"""Clothing parser — per-class semantic segmentation for garments.

Phase V (Fix round 2 — April 2026):
HF serverless `api-inference.huggingface.co` has been retired and the new
`router.huggingface.co/hf-inference` provider does not support custom
community models like `sayeed99/segformer_b3_clothes`. We now run the
model locally via `transformers` on CPU — one-time ~180 MB download,
cached in-process. First call warms the model (≈5 s on this pod),
subsequent calls are ≈2-4 s per image.

Execution order (first hit wins):
  1. Self-hosted endpoint (`CLOTHING_PARSER_ENDPOINT_URL`) — future
     `dressapp.co` GPU box; contract: POST multipart `image` → JSON
     `{segments: [{label, mask (PNG b64), bbox[y,x,y,x 0-1000]?}, ...]}`.
  2. Local transformers + torch CPU (primary).

The function never raises on bad inputs — returns `[]` so the caller
(garment_vision) can fall back to the Gemini detector.

Bounding-box convention: `[ymin, xmin, ymax, xmax]` on a 0..1000 scale
(matches the rest of the pipeline / `_crop_to_bbox`). A `mask` field
(full-size numpy uint8 binary) is also returned so callers can build
alpha-cutout crops rather than raw bbox crops.
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

# ATR/clothes label → our internal category. Labels we don't surface
# (skin, hair, background) are filtered out.
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
# Max edge of the input fed to the model — keeps CPU latency predictable.
_MAX_INPUT_EDGE = 1024

_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)

# --- lazy singleton SegFormer model -------------------------------------
_model_lock = threading.Lock()
_model: Any = None
_processor: Any = None
_id2label: dict[int, str] = {}


def _load_model() -> None:
    global _model, _processor, _id2label
    if _model is not None:
        return
    with _model_lock:
        if _model is not None:
            return
        from transformers import (
            SegformerForSemanticSegmentation,
            SegformerImageProcessor,
        )

        model_id = settings.CLOTHING_PARSER_MODEL
        t0 = time.time()
        logger.info(
            "clothing_parser: loading SegFormer %s locally (first call, ~180MB download on first warm-up)",
            model_id,
        )
        _processor = SegformerImageProcessor.from_pretrained(model_id)
        _model = SegformerForSemanticSegmentation.from_pretrained(model_id)
        _model.eval()
        _id2label = {int(k): v for k, v in _model.config.id2label.items()}
        logger.info(
            "clothing_parser: SegFormer ready in %.1fs (%d classes)",
            time.time() - t0,
            len(_id2label),
        )


def _resize_for_inference(pil: Image.Image) -> Image.Image:
    """Cap the longest side for faster CPU inference. Original-size masks
    are reconstructed by upsampling so we never lose fidelity at crop time."""
    w, h = pil.size
    m = max(w, h)
    if m <= _MAX_INPUT_EDGE:
        return pil
    scale = _MAX_INPUT_EDGE / float(m)
    return pil.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)


def _run_inference(pil_full: Image.Image) -> np.ndarray:
    """Return a class-id mask at the FULL original resolution."""
    import torch

    _load_model()
    pil_small = _resize_for_inference(pil_full)
    inputs = _processor(images=pil_small, return_tensors="pt")
    with torch.no_grad():
        outputs = _model(**inputs)
    logits = outputs.logits  # (1, C, H', W')
    # Upsample directly to the ORIGINAL image size — masks then align
    # pixel-for-pixel with the caller's image.
    target_size = (pil_full.size[1], pil_full.size[0])  # (H, W)
    upsampled = torch.nn.functional.interpolate(
        logits, size=target_size, mode="bilinear", align_corners=False
    )
    pred = upsampled.argmax(dim=1).squeeze(0).cpu().numpy().astype(np.int32)
    return pred


def _split_instances(class_mask: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Split per-class mask into connected-component instances.

    Returns [(label_name, binary_mask_u8), ...]. Mask is same H×W as input.
    Small specks are dropped.
    """
    from scipy import ndimage

    out: list[tuple[str, np.ndarray]] = []
    unique = np.unique(class_mask)
    for cid in unique:
        cid_i = int(cid)
        if cid_i == 0:
            continue  # background in this model
        label_name = _id2label.get(cid_i)
        if not label_name:
            continue
        if _LABEL_MAP.get(label_name) is None:
            continue
        class_binary = (class_mask == cid_i).astype(np.uint8)
        labeled, n = ndimage.label(class_binary)
        # Special-case Left-shoe / Right-shoe — keep ALL connected
        # components (they'll be merged later as same-kind cluster).
        for inst in range(1, n + 1):
            mask = (labeled == inst).astype(np.uint8)
            if mask.sum() >= 128:  # drop tiny noise
                out.append((label_name, mask))
    return out


def _mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return (ymin, xmin, ymax, xmax) of a binary mask in pixel coords."""
    ys, xs = np.where(mask)
    if not len(ys):
        return None
    return int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())


async def _call_self_hosted(
    image_bytes: bytes, endpoint_url: str, img_size: tuple[int, int]
) -> list[dict[str, Any]] | None:
    """Self-hosted contract: POST multipart `image` →
    `{segments: [{label, mask_png_b64, score?}, ...]}`.
    Returns normalised entries in the same shape as parse_garments.
    """
    W, H = img_size
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            resp = await c.post(
                endpoint_url.rstrip("/") + "/segment-clothes",
                files={"image": ("input.jpg", image_bytes, "image/jpeg")},
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("clothing_parser self-hosted exception: %s", exc)
        return None
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
    segments = body.get("segments") or []
    out: list[dict[str, Any]] = []
    total = max(1, W * H)
    for seg in segments:
        label = seg.get("label") or ""
        category = _LABEL_MAP.get(label)
        if not category:
            continue
        mask_b64 = seg.get("mask") or seg.get("mask_png_b64")
        if not mask_b64:
            continue
        try:
            data = base64.b64decode(mask_b64.split(",", 1)[-1])
            im = Image.open(io.BytesIO(data)).convert("L")
            if im.size != (W, H):
                im = im.resize((W, H), Image.NEAREST)
            mask = (np.array(im) > 127).astype(np.uint8)
        except Exception:  # noqa: BLE001
            continue
        area = int(mask.sum())
        if area / total < _MIN_AREA_FRAC:
            continue
        bb = _mask_bbox(mask)
        if bb is None:
            continue
        ymin, xmin, ymax, xmax = bb
        out.append(
            {
                "label": label,
                "category": category,
                "score": float(seg.get("score") or 0.9),
                "bbox": [
                    int(ymin / H * 1000),
                    int(xmin / W * 1000),
                    int(ymax / H * 1000),
                    int(xmax / W * 1000),
                ],
                "mask": mask,
            }
        )
    return out


async def parse_garments(image_bytes: bytes) -> list[dict[str, Any]]:
    """Return [{label, category, score, bbox, mask}] for each garment.

    * `bbox` → `[ymin, xmin, ymax, xmax]` on a 0..1000 scale (matches
      `garment_vision._crop_to_bbox`).
    * `mask` → full-resolution numpy uint8 (1=garment) aligned with the
      original image. Callers use it with `crop_with_mask` to produce
      semantic cutouts instead of bbox squares.

    Empty list means "parser unavailable or found nothing useful"; the
    caller should fall back to the legacy Gemini detector.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.warning("clothing_parser: bad image bytes: %s", exc)
        return []
    W, H = img.size

    # 1. Self-hosted takes precedence (user's future dressapp.co box).
    if settings.CLOTHING_PARSER_ENDPOINT_URL:
        remote = await _call_self_hosted(
            image_bytes, settings.CLOTHING_PARSER_ENDPOINT_URL, (W, H)
        )
        if remote:
            logger.info(
                "clothing_parser: self-hosted produced %d garment(s)", len(remote)
            )
            return remote

    # 2. Local CPU inference — DISABLED by default because the SegFormer
    #    model peaks at ~2 GB RAM during the first forward pass, which
    #    OOM-kills the backend pod on small memory budgets. Enable by
    #    setting USE_LOCAL_CLOTHING_PARSER=true after confirming your
    #    pod has at least 4 GB of headroom.
    if not settings.USE_LOCAL_CLOTHING_PARSER:
        logger.debug(
            "clothing_parser: local inference disabled (USE_LOCAL_CLOTHING_PARSER=false); "
            "returning empty so caller falls back to Gemini detector."
        )
        return []

    t0 = time.time()
    ok = False
    try:
        class_mask = await asyncio.to_thread(_run_inference, img)
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("clothing_parser: local inference failed: %s", exc)
        provider_activity.record(
            "clothing_parser",
            ok=False,
            latency_ms=int((time.time() - t0) * 1000),
            extra={"provider": "local", "err": repr(exc)[:120]},
        )
        return []
    provider_activity.record(
        "clothing_parser",
        ok=ok,
        latency_ms=int((time.time() - t0) * 1000),
        extra={"provider": "local", "model": settings.CLOTHING_PARSER_MODEL},
    )

    instances = await asyncio.to_thread(_split_instances, class_mask)
    total = max(1, W * H)

    # 1) First pass: keep only sufficiently-large instances; index by label.
    by_label: dict[str, dict[str, Any]] = {}
    for label_name, mask in instances:
        if int(mask.sum()) / total < _MIN_AREA_FRAC:
            continue
        if label_name in by_label:
            # Merge disconnected components of the same label into one
            # mask — e.g. a shirt split by a belt, or hair overlapping a
            # sweater — so the UI shows one card per garment.
            by_label[label_name]["mask"] = np.maximum(
                by_label[label_name]["mask"], mask
            )
        else:
            by_label[label_name] = {
                "label": label_name,
                "category": _LABEL_MAP[label_name],
                "score": 0.95,
                "mask": mask,
            }

    # 2) Collapse Left-shoe + Right-shoe into a single "Shoes" item —
    #    users think of them as one pair, and `_looks_already_cropped`
    #    handles single-item footwear photos more cleanly this way.
    left = by_label.pop("Left-shoe", None)
    right = by_label.pop("Right-shoe", None)
    if left or right:
        pair_masks = [x["mask"] for x in (left, right) if x]
        combined = pair_masks[0]
        for m in pair_masks[1:]:
            combined = np.maximum(combined, m)
        by_label["Shoes"] = {
            "label": "Shoes",
            "category": "footwear",
            "score": 0.95,
            "mask": combined,
        }

    # 3) Finalise: compute bboxes from merged masks, emit canonical dict.
    out: list[dict[str, Any]] = []
    for item in by_label.values():
        bb = _mask_bbox(item["mask"])
        if bb is None:
            continue
        ymin, xmin, ymax, xmax = bb
        out.append(
            {
                "label": item["label"],
                "category": item["category"],
                "score": float(item["score"]),
                "bbox": [
                    int(ymin / H * 1000),
                    int(xmin / W * 1000),
                    int(ymax / H * 1000),
                    int(xmax / W * 1000),
                ],
                "mask": item["mask"],
            }
        )
    logger.info(
        "clothing_parser: produced %d garment(s) labels=%s",
        len(out),
        [o["label"] for o in out],
    )
    return out


# ---------------------------------------------------------------------
# Helpers used by garment_vision.analyze_outfit to build cutout crops.
# ---------------------------------------------------------------------
def crop_with_mask(
    image_bytes: bytes,
    bbox_norm: list[int] | tuple[int, ...],
    mask: np.ndarray | None,
    *,
    padding_pct: float = 0.04,
) -> tuple[bytes, tuple[int, int, int, int]] | None:
    """Crop image to bbox+padding, optionally apply mask as alpha channel.

    * `bbox_norm` is `[ymin, xmin, ymax, xmax]` on 0..1000 scale.
    * `mask` is full-resolution binary uint8. When `None`, returns a
      plain JPEG crop (compatible with the legacy bbox path).
    * Returns `(image_bytes, (x1, y1, x2, y2))` or `None` on failure.
      Bytes are PNG when a mask is applied (preserves transparency),
      JPEG otherwise.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:  # noqa: BLE001
        return None
    W, H = img.size
    try:
        ymin, xmin, ymax, xmax = [int(v) for v in bbox_norm]
    except Exception:  # noqa: BLE001
        return None
    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        return None
    x1 = max(0, int(xmin / 1000.0 * W - W * padding_pct))
    y1 = max(0, int(ymin / 1000.0 * H - H * padding_pct))
    x2 = min(W, int(xmax / 1000.0 * W + W * padding_pct))
    y2 = min(H, int(ymax / 1000.0 * H + H * padding_pct))
    if x2 - x1 <= 4 or y2 - y1 <= 4:
        return None

    if mask is None:
        out = img.convert("RGB").crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        out.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue(), (x1, y1, x2, y2)

    # Apply semantic mask as alpha
    rgba = img.convert("RGBA")
    cropped = rgba.crop((x1, y1, x2, y2))
    if mask.shape != (H, W):
        m_resized = np.array(
            Image.fromarray((mask * 255).astype(np.uint8), mode="L").resize(
                (W, H), Image.NEAREST
            )
        )
    else:
        m_resized = (mask * 255).astype(np.uint8)
    mask_crop = m_resized[y1:y2, x1:x2]
    # Combine existing alpha with semantic mask (min = union-of-opaque).
    alpha = np.array(cropped.split()[-1])
    new_alpha = np.minimum(alpha, mask_crop).astype(np.uint8)
    cropped.putalpha(Image.fromarray(new_alpha, mode="L"))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), (x1, y1, x2, y2)
