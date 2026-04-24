"""Background matting — non-generative alpha cutout.

Phase V (Fix round 2 — April 2026):
The original plan to call BiRefNet via the HF serverless Inference API
failed in practice — `api-inference.huggingface.co` has been retired and
BiRefNet is not exposed on the new `router.huggingface.co/hf-inference`
provider ("Model not supported by provider hf-inference").

We now run matting **locally** via the excellent `rembg` library
(MIT-licensed), which bundles BiRefNet and ISNet weights behind an
onnxruntime-CPU session. First call downloads the weights (~170 MB,
cached to ~/.u2net). Subsequent calls are ~2-4 s per image on CPU.

No hallucination is possible: the model emits a per-pixel alpha mask
which we multiply into the original pixels — we never synthesise
new colour values.

Execution order:
  1. Self-hosted endpoint (`BACKGROUND_MATTING_ENDPOINT_URL`) — future
     dressapp.co GPU box.
  2. Local rembg (primary).

The CLIP faithfulness guard is retained but is now advisory — since
rembg cannot hallucinate, the only failure modes are "empty mask" (which
we detect directly) or "too much of the garment got masked out" (which
the CLIP check catches). Threshold is configurable.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
import time
from typing import Any

import httpx
import numpy as np
from PIL import Image

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# Lazy rembg session (the onnx model is heavy; load once per process).
_session_lock = threading.Lock()
_session: Any = None


def _get_session() -> Any:
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:
            return _session
        from rembg import new_session

        model_name = settings.BACKGROUND_MATTING_REMBG_MODEL
        t0 = time.time()
        logger.info(
            "background_matting: loading rembg session model=%s (first call, ~170MB download on first warm-up)",
            model_name,
        )
        try:
            _session = new_session(model_name=model_name)
            logger.info(
                "background_matting: rembg session ready in %.1fs",
                time.time() - t0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "background_matting: failed to create rembg session (%s); feature disabled",
                exc,
            )
            raise
        return _session


def _rembg_remove(image_bytes: bytes) -> bytes | None:
    """Blocking helper — call inside asyncio.to_thread."""
    from rembg import remove

    try:
        sess = _get_session()
        out = remove(image_bytes, session=sess)
        if not out:
            return None
        # Sanity: make sure we got a meaningful alpha mask, not empty.
        try:
            im = Image.open(io.BytesIO(out)).convert("RGBA")
            a = np.array(im.split()[-1])
            opaque_ratio = float((a > 32).sum()) / float(max(1, a.size))
            if opaque_ratio < 0.01:
                logger.info(
                    "background_matting: rejecting near-empty mask (opaque=%.3f)",
                    opaque_ratio,
                )
                return None
        except Exception:  # noqa: BLE001
            # If we can't inspect it, trust the bytes and return.
            pass
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("background_matting: rembg failed (%s)", exc)
        return None


async def _call_self_hosted(image_bytes: bytes, endpoint_url: str) -> bytes | None:
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            resp = await c.post(
                endpoint_url.rstrip("/") + "/remove-background",
                files={"image": ("input.png", image_bytes, "image/png")},
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("background_matting self-hosted exception: %s", exc)
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


async def _faithfulness_ok(original: bytes, matted: bytes) -> bool:
    """CLIP cosine-similarity guard. Any error → treat as OK (don't block).

    Rembg output is deterministic (same pixels, subset only) so the CLIP
    score should stay >0.85 on valid cutouts. A low score means the mask
    eroded something important.
    """
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
    """Return `{image_png, provider, faithful}`.

    * `image_png` is transparent-background PNG bytes, or `None` if all
      paths failed or the faithfulness guard rejected the output.
    * `provider` is `"self_hosted"` or `"local_rembg"`.
    * `faithful` reflects the CLIP sanity check.
    """
    matted: bytes | None = None
    provider: str | None = None

    if settings.BACKGROUND_MATTING_ENDPOINT_URL:
        matted = await _call_self_hosted(
            image_bytes, settings.BACKGROUND_MATTING_ENDPOINT_URL
        )
        provider = "self_hosted"

    if not matted:
        t0 = time.time()
        matted = await asyncio.to_thread(_rembg_remove, image_bytes)
        provider_activity.record(
            "background_matting",
            ok=matted is not None,
            latency_ms=int((time.time() - t0) * 1000),
            extra={
                "provider": "local_rembg",
                "model": settings.BACKGROUND_MATTING_REMBG_MODEL,
            },
        )
        if matted:
            provider = provider or "local_rembg"

    if not matted:
        return {"image_png": None, "provider": provider, "faithful": False}

    ok = await _faithfulness_ok(image_bytes, matted)
    return {
        "image_png": matted if ok else None,
        "provider": provider,
        "faithful": ok,
    }


async def matte_crop(image_bytes: bytes) -> bytes | None:
    """Lightweight variant used by the multi-item analyzer.

    Runs the same rembg pipeline but SKIPS the CLIP faithfulness guard
    (too expensive to run N times in one /analyze request) and returns
    plain PNG bytes on success or `None` on failure. Callers should
    fall back to the original bbox JPEG when this returns None.
    """
    if settings.BACKGROUND_MATTING_ENDPOINT_URL:
        remote = await _call_self_hosted(
            image_bytes, settings.BACKGROUND_MATTING_ENDPOINT_URL
        )
        if remote:
            return remote
    try:
        return await asyncio.to_thread(_rembg_remove, image_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.info("matte_crop failed: %s", exc)
        return None
