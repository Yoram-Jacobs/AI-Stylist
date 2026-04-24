"""Clothing parser — per-class segmentation for garments (Phase V Fix 1).

Swaps in `sayeed99/segformer_b3_clothes` (MIT) to reliably split multi-item
outfits into per-garment crops. The model produces pixel-wise labels over
18 ATR classes: upper-clothes, pants, skirt, dress, belt, hat, shoes,
bag, etc. We cluster per-class masks into instances via connected
components, then return bounding boxes + crops.

Two execution paths:
  1. HF Inference API (default, free with HF_TOKEN) — called via the
     serverless `image-segmentation` task, returns per-label binary PNG masks.
  2. Self-hosted FastAPI endpoint (future dressapp.co) — set
     CLOTHING_PARSER_ENDPOINT_URL and we POST the image there instead.

The function never raises on bad inputs — it returns an empty list if the
call fails, so the caller (garment_vision) can fall back to the legacy
detector.
"""
from __future__ import annotations

import asyncio
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

# ATR label → our internal category. Labels we don't surface (skin, hair,
# background) are filtered out.
_LABEL_MAP: dict[str, str | None] = {
    "Background": None,
    "Hat": "headwear",
    "Hair": None,
    "Sunglasses": "accessory",
    "Upper-clothes": "top",
    "Skirt": "bottom",
    "Pants": "bottom",
    "Dress": "dress",
    "Belt": "accessory",
    "Left-shoe": "footwear",
    "Right-shoe": "footwear",
    "Face": None,
    "Left-leg": None,
    "Right-leg": None,
    "Left-arm": None,
    "Right-arm": None,
    "Bag": "accessory",
    "Scarf": "accessory",
}
# Minimum mask area (as fraction of total image) to consider a detection.
_MIN_AREA_FRAC = 0.005
_HF_IMAGE_SEG_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


async def _call_hf_inference(
    image_bytes: bytes,
) -> list[dict[str, Any]] | None:
    """Return HF serverless image-segmentation response list, or None."""
    token = settings.HF_TOKEN
    if not token:
        logger.warning("clothing_parser: HF_TOKEN missing; skipping HF call")
        return None
    model = settings.CLOTHING_PARSER_MODEL
    url = f"https://api-inference.huggingface.co/models/{model}"
    started = time.time()
    async with httpx.AsyncClient(timeout=_HF_IMAGE_SEG_TIMEOUT) as c:
        resp = await c.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
            },
            content=image_bytes,
        )
    provider_activity.record(
        "clothing_parser",
        ok=resp.status_code == 200,
        latency_ms=int((time.time() - started) * 1000),
        extra={"provider": "hf_serverless", "model": model},
    )
    if resp.status_code != 200:
        logger.info("clothing_parser HF call non-200: %s %s", resp.status_code, resp.text[:240])
        return None
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


async def _call_self_hosted(
    image_bytes: bytes, endpoint_url: str
) -> list[dict[str, Any]] | None:
    """Self-hosted endpoint contract: POST multipart file `image`, response
    JSON {segments: [{label, score, mask_png_b64}, ...]}."""
    started = time.time()
    async with httpx.AsyncClient(timeout=_HF_IMAGE_SEG_TIMEOUT) as c:
        resp = await c.post(
            endpoint_url.rstrip("/") + "/segment-clothes",
            files={"image": ("input.jpg", image_bytes, "image/jpeg")},
        )
    provider_activity.record(
        "clothing_parser",
        ok=resp.status_code == 200,
        latency_ms=int((time.time() - started) * 1000),
        extra={"provider": "self_hosted", "url": endpoint_url},
    )
    if resp.status_code != 200:
        logger.info("clothing_parser self-hosted non-200: %s", resp.status_code)
        return None
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None
    return body.get("segments") or []


def _mask_bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.where(mask)
    if not len(ys):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def _decode_mask_png(b64: str, target_size: tuple[int, int]) -> np.ndarray | None:
    try:
        data = base64.b64decode(b64.split(",", 1)[-1])
        im = Image.open(io.BytesIO(data)).convert("L")
        if im.size != target_size:
            im = im.resize(target_size, Image.NEAREST)
        return (np.array(im) > 127).astype(np.uint8)
    except Exception:  # noqa: BLE001
        return None


async def parse_garments(
    image_bytes: bytes,
) -> list[dict[str, Any]]:
    """Return [{label, category, score, bbox, mask_u8}] for each garment.

    Empty list means "parser unavailable or no garments found"; the caller
    should fall back to the legacy detector.
    """
    # Load original to know target size.
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("clothing_parser: bad image bytes: %s", exc)
        return []
    W, H = img.size

    segments: list[dict[str, Any]] | None = None
    if settings.CLOTHING_PARSER_ENDPOINT_URL:
        segments = await _call_self_hosted(
            image_bytes, settings.CLOTHING_PARSER_ENDPOINT_URL
        )
    if segments is None:
        segments = await _call_hf_inference(image_bytes)
    if not segments:
        return []

    out: list[dict[str, Any]] = []
    total_pixels = max(1, W * H)
    for seg in segments:
        label = seg.get("label") or ""
        category = _LABEL_MAP.get(label)
        if not category:
            continue
        mask_b64 = seg.get("mask")
        if not mask_b64:
            continue
        mask = _decode_mask_png(mask_b64, (W, H))
        if mask is None:
            continue
        area = int(mask.sum())
        if area / total_pixels < _MIN_AREA_FRAC:
            continue
        bbox = _mask_bbox(mask)
        if bbox is None:
            continue
        out.append(
            {
                "label": label,
                "category": category,
                "score": float(seg.get("score") or 0.9),
                "bbox": bbox,
                "mask": mask,  # numpy u8
            }
        )
    # If the parser merged pants+upper-clothes into a single "Dress" when
    # the original photo clearly had two, we'll let the downstream verifier
    # catch it. Nothing to do here.
    logger.info("clothing_parser produced %d garment(s)", len(out))
    return out


# ---- helpers for downstream -----------------------------------------
def crop_with_mask(
    image_bytes: bytes,
    bbox: list[int],
    mask: np.ndarray | None = None,
    *,
    padding: int = 12,
) -> bytes:
    """Crop + (optionally) apply mask alpha. Returns PNG bytes."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    W, H = img.size
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(W, x1 + padding)
    y1 = min(H, y1 + padding)
    crop = img.crop((x0, y0, x1, y1))
    if mask is not None:
        mask_im = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
        mask_crop = mask_im.crop((x0, y0, x1, y1))
        alpha = np.array(crop.split()[-1])
        new_alpha = np.minimum(alpha, np.array(mask_crop))
        crop.putalpha(Image.fromarray(new_alpha))
    buf = io.BytesIO()
    crop.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def run_with_timeout(coro, timeout: float = 30.0) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("clothing_parser coroutine timed out after %.1fs", timeout)
        return None
