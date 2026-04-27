"""Wardrobe Reconstructor (Phase Q).

Takes a potentially-bad garment crop (from the multi-item extractor or a
single upload) and decides whether it needs reconstruction. When it does,
we prefer **Nano Banana** (`gemini-2.5-flash-image`, native Google SDK,
requires ``GEMINI_API_KEY``) and fall back to **HF FLUX.1-schnell** when
the direct Gemini key isn't configured (dev preview).

Public API
----------
* ``should_reconstruct(analysis, bbox, frame_size) -> (bool, list[str])``
  Fast, local heuristics. Returns ``(needs_repair, reasons)``.
* ``reconstruct(crop_bytes, analysis, *, validate=True) -> dict | None``
  Runs the chosen reconstructor with a composed prompt and (optionally)
  sanity-checks the output by re-analysing the generated image. Returns
  ``{image_b64, mime_type, prompt, validated, rejected_reason}`` or
  ``None`` on unrecoverable failure.

All calls soft-fail so the upstream analyse pipeline never errors because
of a reconstruction hiccup.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.gemini_image_service import gemini_image_service
from app.services.hf_image_service import hf_image_service

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- heuristics

# A bbox side within this many normalised units of the frame edge is
# considered "touching" (the detector couldn't see beyond the frame).
_EDGE_TOUCH_MARGIN = 30  # on the 0..1000 Gemini scale = 3% of frame.

# Category priors for expected crop aspect ratio (height / width).
# Used to catch the "squareish dress crop" case where the detector
# clipped the hem and produced a too-wide bbox.
_CATEGORY_ASPECT_MIN = {
    "dress": 1.15,
    "outerwear": 1.05,
    "top": 0.80,
    "bottom": 1.00,
    "shoes": 0.55,
    "footwear": 0.55,
    "accessory": 0.40,
    "bag": 0.60,
}

# If a crop covers less than this fraction of the frame AND it was
# detected as a large-category piece (dress/outerwear/bottom), we
# consider it under-captured.
_SMALL_CROP_THRESHOLD = 0.12
_LARGE_CATEGORIES = {"dress", "outerwear", "bottom"}


def _norm_category(raw: str | None) -> str:
    return (raw or "").strip().lower()


def should_reconstruct(
    analysis: dict[str, Any],
    bbox_norm: list[int] | None,
    frame_size: tuple[int, int] | None = None,
) -> tuple[bool, list[str]]:
    """Decide whether a crop should be sent to the reconstructor.

    Args:
        analysis: the GarmentAnalysis JSON produced by The Eyes
          (must contain at least ``category``; optional
          ``sub_category`` / ``item_type``).
        bbox_norm: ``[ymin, xmin, ymax, xmax]`` on the 0..1000 Gemini
          scale. ``None`` means "no bbox available", which is the case
          for single-upload items — we return ``(False, [])`` because
          we have no frame context to judge quality.
        frame_size: (w, h) of the original uploaded image. Only used for
          shape metadata; the heuristics here operate on normalised
          bbox coordinates.

    Returns:
        ``(needs_repair, reasons)`` — ``reasons`` is a list of short
        string tokens suitable for logging / UI display.
    """
    del frame_size  # reserved for future pixel-level checks
    reasons: list[str] = []
    if not bbox_norm or len(bbox_norm) != 4:
        return False, reasons

    try:
        ymin, xmin, ymax, xmax = [int(v) for v in bbox_norm]
    except (TypeError, ValueError):
        return False, reasons

    width = max(1, xmax - xmin)
    height = max(1, ymax - ymin)
    area = width * height
    area_frac = area / (1000.0 * 1000.0)
    aspect = height / float(width)
    category = _norm_category(analysis.get("category"))

    # Rule 1: a near-full-frame bbox means the user uploaded an already
    # clean product shot. Per spec: "Neglect item images that show the
    # whole item without bg and without other items."
    if area_frac >= 0.85:
        return False, ["whole_frame_skip"]

    # Rule 2: bbox touching any edge -> garment likely extends off-canvas.
    if ymin <= _EDGE_TOUCH_MARGIN:
        reasons.append("edge_touch_top")
    if xmin <= _EDGE_TOUCH_MARGIN:
        reasons.append("edge_touch_left")
    if ymax >= 1000 - _EDGE_TOUCH_MARGIN:
        reasons.append("edge_touch_bottom")
    if xmax >= 1000 - _EDGE_TOUCH_MARGIN:
        reasons.append("edge_touch_right")

    # Rule 3: aspect-ratio mismatch against the expected category prior.
    if category in _CATEGORY_ASPECT_MIN:
        min_aspect = _CATEGORY_ASPECT_MIN[category]
        # Only flag dresses/outerwear/bottoms when they came back too
        # wide; being TALLER than the prior is always fine.
        if category in _LARGE_CATEGORIES and aspect < min_aspect * 0.85:
            reasons.append(f"aspect_mismatch_{category}")

    # Rule 4: tiny crop of a large-category garment.
    if category in _LARGE_CATEGORIES and area_frac < _SMALL_CROP_THRESHOLD:
        reasons.append("undersized_crop")

    return (len(reasons) > 0), reasons


# --------------------------------------------------------------------- generator

def _build_reconstruction_prompt(analysis: dict[str, Any]) -> str:
    """Compose a high-fidelity product-shot prompt from an analysis."""
    bits: list[str] = []
    for key in ("color", "material", "pattern", "sub_category", "item_type"):
        v = analysis.get(key)
        if v:
            bits.append(str(v))
    descriptor = " ".join(bits) if bits else (
        analysis.get("category") or analysis.get("title") or "garment"
    )
    title = analysis.get("title") or analysis.get("name") or ""
    extras: list[str] = []
    if analysis.get("brand"):
        extras.append(f"by {analysis['brand']}")
    if analysis.get("dress_code"):
        extras.append(f"{analysis['dress_code']} style")
    extras_str = (", " + ", ".join(extras)) if extras else ""
    prompt = (
        f"High-fidelity editorial product photograph of a complete, "
        f"full-length {descriptor}"
        f"{(': ' + title) if title else ''}"
        f"{extras_str}. Studio lighting, plain off-white backdrop, "
        "garment-only product shot, centered composition, sharp focus, "
        "photorealistic, preserve fabric texture and pattern details, "
        "no people, no mannequin body, no text, no logos, no watermarks."
    )
    return prompt[:1000]


async def reconstruct(
    crop_bytes: bytes,
    analysis: dict[str, Any],
    *,
    reasons: list[str] | None = None,
    validate: bool = True,
) -> dict[str, Any] | None:
    """Run the HF FLUX reconstructor on a crop and return a data payload.

    The returned dict has:
        image_b64:       base64 PNG of the repaired image
        mime_type:       image/png
        prompt:          the composed text prompt used
        model:           HF model id
        reasons:         which heuristics triggered repair
        validated:       True if the post-gen sanity check accepted the
                         result; False if we rejected it (caller should
                         fall back to the original crop).
        rejected_reason: optional explanation when ``validated=False``.

    On a pipeline-level failure we return ``None`` and log a warning —
    the caller must keep using the original crop.
    """
    # Prefer Nano Banana when a direct Gemini key is configured (better
    # quality, no hallucinated category drift). Fall back to HF FLUX in
    # dev preview where only the Emergent key is available.
    image_service = gemini_image_service or hf_image_service
    if image_service is None:
        return None
    using = "nano-banana" if image_service is gemini_image_service else "hf-flux"
    prompt = _build_reconstruction_prompt(analysis)
    try:
        out = await image_service.edit(
            crop_bytes,
            prompt,
            garment_metadata={
                "title": analysis.get("title"),
                "category": analysis.get("category"),
                "sub_category": analysis.get("sub_category"),
                "color": analysis.get("color"),
                "material": analysis.get("material"),
                "pattern": analysis.get("pattern"),
                "brand": analysis.get("brand"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Reconstruction edit failed (engine=%s): %s",
            using,
            repr(exc)[:200],
        )
        return None
    image_b64 = out.get("image_b64")
    if not image_b64:
        return None

    validated = True
    rejected_reason: str | None = None
    if validate:
        try:
            import base64 as _b64
            from app.services.garment_vision import garment_vision_service

            if garment_vision_service is not None:
                generated_bytes = _b64.b64decode(image_b64)
                new_analysis = await garment_vision_service.analyze(
                    generated_bytes,
                    model=garment_vision_service.crop_model,
                )
                orig_cat = _norm_category(analysis.get("category"))
                new_cat = _norm_category(new_analysis.get("category"))
                # Accept only when the top-level category still matches.
                # sub_category / item_type drift is OK.
                if orig_cat and new_cat and orig_cat != new_cat:
                    validated = False
                    rejected_reason = (
                        f"category drift {orig_cat!r} -> {new_cat!r}"
                    )
                    logger.info("Reconstruction rejected: %s", rejected_reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reconstruction validation skipped (analyze failed): %s",
                repr(exc)[:160],
            )

    return {
        "image_b64": image_b64,
        "mime_type": out.get("mime_type", "image/png"),
        "prompt": prompt,
        "model": out.get("model_used"),
        "engine": using,
        "reasons": reasons or [],
        "validated": validated,
        "rejected_reason": rejected_reason,
    }
