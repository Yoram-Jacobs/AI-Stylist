"""Tiny, reusable thumbnail generator for closet list responses.

Problem
-------
Closet items persist the full segmented / reconstructed images as
``data:image/...;base64,...`` URLs embedded directly inside the Mongo
document. A single item's ``reconstructed_image_url`` is routinely
800-1500 KB, so a 40-item closet response balloons to 25-60 MB of JSON
— which is exactly why ``GET /api/v1/closet`` takes 30 s even after the
DB sort was fixed.

Solution
--------
For every item, the first time the list endpoint observes it without a
``thumbnail_data_url``, this module:

1. Picks the best source image (reconstructed > segmented > original).
2. Decodes the base64, downsizes to ``MAX_THUMB_SIZE``, re-encodes as
   a JPEG at ``THUMB_QUALITY``.
3. Returns a short ``data:image/jpeg;base64,...`` URL (~10-18 KB).

The caller is expected to persist the result back to the document so
subsequent reads skip the work entirely.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# Target dimensions for the closet grid card. The frontend renders 3:4
# cards at roughly 220×290 CSS px (and up to 2× on retina), so 320×426
# is a safe upper bound that still keeps file size tiny.
MAX_THUMB_SIZE = (320, 426)
THUMB_QUALITY = 70  # JPEG quality — 70 is visually indistinguishable for thumbnails


def _decode_data_url(data_url: str) -> bytes | None:
    """Extract the raw bytes from a ``data:...;base64,XXX`` URL."""
    if not isinstance(data_url, str):
        return None
    if not data_url.startswith("data:"):
        return None
    try:
        _, b64 = data_url.split(",", 1)
    except ValueError:
        return None
    try:
        return base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None


def _has_meaningful_alpha(img: Image.Image) -> bool:
    """Return True when the image has any non-fully-opaque pixels.

    A garment cutout from rembg/SegFormer is RGBA with most pixels
    transparent and the garment opaque. A photo accidentally opened as
    RGBA might also be RGBA but with all alpha == 255 (no actual
    transparency). We only want to keep PNG output for the former.
    """
    if img.mode not in ("RGBA", "LA"):
        return False
    try:
        alpha = img.split()[-1]
        # ``getextrema()`` returns ``(min, max)`` for an L-mode band.
        lo, hi = alpha.getextrema()
        return lo < 255  # any pixel that isn't fully opaque
    except Exception:  # noqa: BLE001
        return False


def _downsize_bytes(raw: bytes) -> bytes | None:
    """Decode → shrink → re-encode. Returns ``None`` on any error.

    PNGs with real transparency (rembg cutouts, SegFormer-masked PNGs)
    are kept as PNG so the closet grid renders them on the page
    background instead of mashing them onto an opaque colour. Fully-
    opaque inputs become JPEG to keep payload tiny.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        # Flatten palette images so we can inspect their alpha properly.
        if img.mode == "P":
            img = img.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        logger.info("thumbnail decode failed: %s", repr(exc)[:120])
        return None
    try:
        keep_alpha = _has_meaningful_alpha(img)
        if keep_alpha:
            # Resize the RGBA image directly — Pillow handles alpha
            # downsampling correctly with LANCZOS.
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.thumbnail(MAX_THUMB_SIZE, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        # No alpha to preserve — JPEG keeps the closet payload small.
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(MAX_THUMB_SIZE, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=THUMB_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.info("thumbnail resize failed: %s", repr(exc)[:120])
        return None


def make_thumb_from_data_url(data_url: str) -> str | None:
    """Synchronous core — data URL in, data URL out (or ``None`` on failure).

    Returns a ``data:image/png;base64,...`` URL when the source has
    real transparency, otherwise ``data:image/jpeg;base64,...``.
    """
    raw = _decode_data_url(data_url)
    if not raw:
        return None
    small = _downsize_bytes(raw)
    if not small:
        return None
    # Sniff the encoded format (first byte of PNG vs JPEG marker).
    is_png = small[:8] == b"\x89PNG\r\n\x1a\n"
    mime = "image/png" if is_png else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(small).decode("ascii")


def pick_source_data_url(item: dict[str, Any]) -> str | None:
    """Return the best image URL on an item for thumbnail purposes.

    Priority: reconstructed (cleanest) → segmented → original.
    Only returns values that look like ``data:image/...`` URLs; anything
    already pointing at a CDN is passed through untouched elsewhere.
    """
    for key in (
        "reconstructed_image_url",
        "segmented_image_url",
        "original_image_url",
    ):
        v = item.get(key)
        if isinstance(v, str) and v.startswith("data:image"):
            return v
    return None


async def ensure_thumbnail(item: dict[str, Any]) -> str | None:
    """Return a thumbnail data URL for ``item``, generating it if absent.

    Does **not** touch the database — caller is responsible for
    persisting the result (so a background list scan can batch-update).

    Returns ``None`` when no source image is available, in which case
    the frontend falls back to its placeholder.

    Stale-thumbnail invalidation: if the cached thumbnail is JPEG but
    the source image is a transparent PNG (a rembg/SegFormer cutout),
    we regenerate it. This handles items that were saved before the
    "preserve transparency" fix shipped — without that, those closet
    cards would forever show the garment composited onto grey.
    """
    existing = item.get("thumbnail_data_url")
    source = pick_source_data_url(item)
    if isinstance(existing, str) and existing.startswith("data:image"):
        # Detect stale thumbs: source is PNG (likely transparent) but
        # the cached thumb is JPEG → regenerate to recover transparency.
        source_is_png = isinstance(source, str) and source.startswith("data:image/png")
        thumb_is_jpeg = existing.startswith("data:image/jpeg")
        if not (source_is_png and thumb_is_jpeg):
            return existing
        logger.info("regenerating stale thumbnail (source PNG → cached thumb was JPEG)")
    if not source:
        return None
    return await asyncio.to_thread(make_thumb_from_data_url, source)


async def backfill_thumbnails(
    items: list[dict[str, Any]],
    *,
    concurrency: int = 4,
) -> list[tuple[str, str]]:
    """Generate thumbnails for any items missing one. Returns ``(item_id, thumb)``
    pairs so the caller can persist them in one batched Mongo update.

    Runs with bounded concurrency so a large first-load doesn't spike
    CPU or saturate the thread pool.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(it: dict[str, Any]) -> tuple[str, str] | None:
        # Reuse ensure_thumbnail's freshness logic so stale JPEGs over
        # transparent PNG sources get regenerated automatically.
        async with sem:
            thumb = await ensure_thumbnail(it)
        if not thumb:
            return None
        if thumb == it.get("thumbnail_data_url"):
            return None  # unchanged
        it["thumbnail_data_url"] = thumb
        return (it.get("id", ""), thumb) if it.get("id") else None

    results = await asyncio.gather(*[_one(it) for it in items], return_exceptions=True)
    pairs: list[tuple[str, str]] = []
    for r in results:
        if isinstance(r, tuple):
            pairs.append(r)
    return pairs
