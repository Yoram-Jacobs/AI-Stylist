"""Background matting — non-generative alpha cutout (Phase V Fix 2).

Replaces the old "Repair image" generative inpainting (which hallucinated
details — e.g. inventing a red shorts to match a red shirt) with a pure
alpha-matting pipeline. The model decides which pixels are garment vs
background; it never invents pixels.

Two paths like the parser:
  1. Self-hosted endpoint (preferred, future dressapp.co) —
     BACKGROUND_MATTING_ENDPOINT_URL is set, we POST the crop and get back
     a PNG with transparent background.
  2. HF Inference API (fallback). Note: BiRefNet isn't natively exposed on
     the serverless Inference API at time of writing; this path returns
     None and callers fall back to the pre-matted mask we already have
     from the clothing parser step.

Faithfulness guard: a CLIP-embedding cosine check compares original crop
vs matted result. If similarity < MATTING_FAITHFULNESS_THRESHOLD we
reject the matting (returns None) and caller keeps the original.
"""
from __future__ import annotations

import base64
import io
import logging
import time
from typing import Any

import httpx
import numpy as np
from PIL import Image

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


async def _call_self_hosted(image_bytes: bytes, endpoint_url: str) -> bytes | None:
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post(
                endpoint_url.rstrip("/") + "/remove-background",
                files={"image": ("input.png", image_bytes, "image/png")},
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("background_matting self-hosted failed: %s", exc)
        provider_activity.record(
            "background_matting",
            ok=False,
            latency_ms=int((time.time() - started) * 1000),
            extra={"provider": "self_hosted", "err": str(exc)[:80]},
        )
        return None
    provider_activity.record(
        "background_matting",
        ok=resp.status_code == 200,
        latency_ms=int((time.time() - started) * 1000),
        extra={"provider": "self_hosted"},
    )
    if resp.status_code != 200:
        return None
    ct = resp.headers.get("content-type", "")
    if ct.startswith("image/"):
        return resp.content
    # JSON with base64
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    b64 = body.get("image_png_b64") or body.get("image")
    if not b64:
        return None
    try:
        return base64.b64decode(b64.split(",", 1)[-1])
    except Exception:  # noqa: BLE001
        return None


async def _call_hf_inference(image_bytes: bytes) -> bytes | None:
    """HF serverless attempt. Most BiRefNet deployments on HF return a PNG
    directly; some return JSON with mask. Try both shapes."""
    token = settings.HF_TOKEN
    if not token:
        return None
    model = settings.BACKGROUND_MATTING_MODEL
    url = f"https://api-inference.huggingface.co/models/{model}"
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "*/*",
                    "Content-Type": "application/octet-stream",
                },
                content=image_bytes,
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("background_matting HF call exception: %s", exc)
        return None
    provider_activity.record(
        "background_matting",
        ok=resp.status_code == 200,
        latency_ms=int((time.time() - started) * 1000),
        extra={"provider": "hf_serverless", "model": model},
    )
    if resp.status_code != 200:
        logger.info(
            "background_matting HF non-200 %s %s",
            resp.status_code,
            resp.text[:160],
        )
        return None
    ct = resp.headers.get("content-type", "")
    if ct.startswith("image/"):
        # Some HF endpoints return a PNG with alpha already set.
        return resp.content
    # If it returned a segmentation list ([{label, mask}, ...]) we take the
    # first non-background mask and apply as alpha to the input.
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, list) and data:
        try:
            first = next(
                (d for d in data if (d.get("label") or "").lower() != "background"),
                data[0],
            )
            mask_b64 = first.get("mask")
            if not mask_b64:
                return None
            mask_png = base64.b64decode(mask_b64.split(",", 1)[-1])
            return _apply_mask_alpha(image_bytes, mask_png)
        except Exception:  # noqa: BLE001
            return None
    return None


def _apply_mask_alpha(rgb_png: bytes, mask_png: bytes) -> bytes | None:
    try:
        img = Image.open(io.BytesIO(rgb_png)).convert("RGBA")
        mask = Image.open(io.BytesIO(mask_png)).convert("L").resize(img.size)
        img.putalpha(mask)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


async def _faithfulness_ok(original: bytes, matted: bytes) -> bool:
    """CLIP cosine-similarity guard. Any error → treat as OK (don't block)."""
    try:
        from app.services import fashion_clip

        svc = fashion_clip._get_service()  # noqa: SLF001
        if svc is None:
            return True
        a = await svc.embed_image(original)
        b = await svc.embed_image(matted)
        if a is None or b is None:
            return True
        a_np = np.asarray(a, dtype=np.float32)
        b_np = np.asarray(b, dtype=np.float32)
        denom = float(np.linalg.norm(a_np) * np.linalg.norm(b_np)) or 1.0
        cos = float(np.dot(a_np, b_np) / denom)
        ok = cos >= settings.MATTING_FAITHFULNESS_THRESHOLD
        logger.info(
            "background_matting faithfulness cos=%.3f threshold=%.3f ok=%s",
            cos,
            settings.MATTING_FAITHFULNESS_THRESHOLD,
            ok,
        )
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.info("faithfulness check skipped: %s", exc)
        return True


async def remove_background(image_bytes: bytes) -> dict[str, Any]:
    """Return {image_png: bytes|None, provider: str, faithful: bool}.

    `image_png=None` means all paths failed and the caller should keep
    the original crop. `faithful=False` means matting ran but the
    verifier rejected it (also return None to caller).
    """
    matted: bytes | None = None
    provider = None
    if settings.BACKGROUND_MATTING_ENDPOINT_URL:
        matted = await _call_self_hosted(
            image_bytes, settings.BACKGROUND_MATTING_ENDPOINT_URL
        )
        provider = "self_hosted"
    if not matted:
        matted = await _call_hf_inference(image_bytes)
        provider = provider or "hf_serverless"
    if not matted:
        return {"image_png": None, "provider": provider, "faithful": False}
    ok = await _faithfulness_ok(image_bytes, matted)
    return {
        "image_png": matted if ok else None,
        "provider": provider,
        "faithful": ok,
    }
