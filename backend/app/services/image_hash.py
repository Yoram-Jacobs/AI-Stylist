"""
Phase Z2 — perceptual image hashing helpers.

Used by /closet/preflight to detect duplicate uploads even when:
  * the existing item's "original_image_url" was never stored (legacy
    items keep only a thumbnail / segmented preview);
  * the user re-exports their photo at a different JPEG quality;
  * the user takes a slightly different shot of the same garment
    (similar angle, similar lighting).

Implementation: a 64-bit average-hash (aHash) PLUS a small RGB colour
signature so two same-shape garments of *different colours* (e.g. navy
shorts vs grey shorts) are NOT flagged as duplicates. Cheap (~3 ms per
image on a typical pod), no extra dependencies — only Pillow + numpy,
both already in requirements.txt.

Match decision:
  * Hamming distance ≤ 6 bits on the shape hash, AND
  * Manhattan distance ≤ ``DEFAULT_COLOR_THRESHOLD`` on the colour
    signature (sum of |Δr| + |Δg| + |Δb| over the 4 quadrants,
    each channel 0–255 = max 4 × 255 × 3 = 3060).
"""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Hash size: 8x8 = 64 bits. Yields a 16-char hex digest. Distances
# are Hamming bit-counts (max 64).
_HASH_SIZE = 8

# Default match threshold for /preflight. ≤ 6 bits (~9% of 64)
# empirically corresponds to "obvious re-upload of the same photo
# even after JPEG re-compression". Higher = more matches but more
# false positives.
DEFAULT_HAMMING_THRESHOLD = 6

# Colour signature: average RGB per quadrant → 4 quadrants × 3 channels
# = 12 bytes = 24 hex chars. Manhattan distance is on the raw byte
# values (0–255). 220 ≈ "noticeably different colour family" empirically:
# navy↔grey scores ~600+, two photos of the same navy garment under
# different lighting score ~80–150.
_COLOR_GRID = 2  # 2x2 grid of quadrants
DEFAULT_COLOR_THRESHOLD = 220


_DATA_URL_RE = re.compile(r"^data:image/[^;]+;base64,(.*)$", re.I)


def _decode_to_pil(image_data: str | bytes | None) -> Optional[Image.Image]:
    """Accept either a data URL string, a bare base64 string, or raw
    bytes. Returns a PIL Image in RGB or None on failure (so callers
    can simply skip)."""
    if image_data is None:
        return None
    try:
        if isinstance(image_data, bytes):
            raw = image_data
        else:
            m = _DATA_URL_RE.match(image_data.strip())
            payload = m.group(1) if m else image_data.strip()
            raw = base64.b64decode(payload, validate=False)
        img = Image.open(io.BytesIO(raw))
        # Convert palette / RGBA / etc. to RGB so .convert('L') below
        # behaves consistently across formats.
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    except Exception as exc:  # noqa: BLE001
        logger.debug("phash decode failed: %s", exc)
        return None


def average_hash(image_data) -> Optional[str]:
    """Compute a 64-bit average-hash of the given image and return it
    as a 16-char lowercase hex string. ``None`` means the input was
    unreadable (we keep going rather than blowing up the upload)."""
    img = _decode_to_pil(image_data)
    if img is None:
        return None
    try:
        small = img.convert("L").resize(
            (_HASH_SIZE, _HASH_SIZE), Image.Resampling.LANCZOS
        )
        arr = np.asarray(small, dtype=np.uint8)
        avg = arr.mean()
        bits = (arr > avg).flatten().astype(np.uint8)
        # Pack 64 bits → 8 bytes → 16 hex chars
        packed = np.packbits(bits)
        return packed.tobytes().hex()
    except Exception as exc:  # noqa: BLE001
        logger.debug("phash compute failed: %s", exc)
        return None


def color_signature(image_data) -> Optional[str]:
    """Compute a coarse RGB colour signature: average colour per
    quadrant (2x2 grid), packed as 12 bytes = 24 hex chars.

    The phash above throws away colour by converting to greyscale —
    that's intentional for matching the *same garment* across
    lighting changes, but it's the reason a navy and a grey pair of
    shorts of the same cut produce near-identical hashes. The colour
    signature recovers enough chroma information to tell those apart
    without sacrificing the phash's robustness.
    """
    img = _decode_to_pil(image_data)
    if img is None:
        return None
    try:
        # Resize to a tiny grid then read average colour per cell.
        # 16x16 is large enough to be representative but small enough
        # that the operation is sub-millisecond.
        small = img.resize((16, 16), Image.Resampling.LANCZOS)
        arr = np.asarray(small, dtype=np.uint8)  # shape (16, 16, 3)
        cell = 16 // _COLOR_GRID  # 8
        out: list[int] = []
        for gy in range(_COLOR_GRID):
            for gx in range(_COLOR_GRID):
                block = arr[
                    gy * cell : (gy + 1) * cell,
                    gx * cell : (gx + 1) * cell,
                    :,
                ]
                # Per-channel mean → 3 ints (0–255 each)
                mean = block.reshape(-1, 3).mean(axis=0).astype(np.uint8)
                out.extend(int(c) for c in mean)
        return bytes(out).hex()
    except Exception as exc:  # noqa: BLE001
        logger.debug("color signature compute failed: %s", exc)
        return None


def compute_signatures(image_data) -> tuple[str | None, str | None]:
    """Decode the image once and return both an aHash and a colour
    signature. Used by the lazy backfill in /preflight where decoding
    is by far the dominant cost — calling ``average_hash`` and
    ``color_signature`` separately re-decodes the same data URL twice
    per row, which on a 300-item closet adds up to multi-second
    request latency. This helper halves that.
    """
    img = _decode_to_pil(image_data)
    if img is None:
        return (None, None)
    ph: str | None = None
    cs: str | None = None
    try:
        small = img.convert("L").resize(
            (_HASH_SIZE, _HASH_SIZE), Image.Resampling.LANCZOS
        )
        arr = np.asarray(small, dtype=np.uint8)
        avg = arr.mean()
        bits = (arr > avg).flatten().astype(np.uint8)
        ph = np.packbits(bits).tobytes().hex()
    except Exception as exc:  # noqa: BLE001
        logger.debug("phash compute failed: %s", exc)
    try:
        small = img.resize((16, 16), Image.Resampling.LANCZOS)
        arr = np.asarray(small, dtype=np.uint8)
        cell = 16 // _COLOR_GRID
        out: list[int] = []
        for gy in range(_COLOR_GRID):
            for gx in range(_COLOR_GRID):
                block = arr[
                    gy * cell : (gy + 1) * cell,
                    gx * cell : (gx + 1) * cell,
                    :,
                ]
                mean = block.reshape(-1, 3).mean(axis=0).astype(np.uint8)
                out.extend(int(c) for c in mean)
        cs = bytes(out).hex()
    except Exception as exc:  # noqa: BLE001
        logger.debug("color signature compute failed: %s", exc)
    return (ph, cs)


def hamming_distance(a: str | None, b: str | None) -> int:
    """Hamming bit-distance between two 16-char hex digests. Returns
    a sentinel (65) for any malformed input so callers can treat it
    as "not a match" without special-casing."""
    if not a or not b or len(a) != len(b):
        return 65
    try:
        ai = int(a, 16)
        bi = int(b, 16)
        return (ai ^ bi).bit_count()
    except ValueError:
        return 65


def color_distance(a: str | None, b: str | None) -> int:
    """Manhattan distance between two colour signatures (24 hex chars
    each). Returns a sentinel (10_000) for malformed input. Range:
    0 (identical) to 4 × 3 × 255 = 3060 (full spectrum apart).

    We use Manhattan over Euclidean because each channel is bounded
    and the threshold is easier to reason about: ~220 ≈ "different
    colour family across the garment surface".
    """
    if not a or not b or len(a) != len(b):
        return 10_000
    try:
        ab = bytes.fromhex(a)
        bb = bytes.fromhex(b)
    except ValueError:
        return 10_000
    return int(sum(abs(int(x) - int(y)) for x, y in zip(ab, bb, strict=False)))


def is_duplicate_match(
    sha_a: str | None,
    sha_b: str | None,
    phash_a: str | None,
    phash_b: str | None,
    color_a: str | None,
    color_b: str | None,
    *,
    hamming_threshold: int = DEFAULT_HAMMING_THRESHOLD,
    color_threshold: int = DEFAULT_COLOR_THRESHOLD,
) -> bool:
    """Single source of truth for "are these two images duplicates?".

    Decision tree:
      1. Exact SHA-256 match → duplicate (re-upload of the exact bytes).
      2. Shape similar (Hamming ≤ threshold) AND
         (no colour sigs available OR colour distance ≤ threshold) → duplicate.
      3. Otherwise → not a duplicate.

    Rule (2)'s colour gate is the fix for "navy shorts flagged as a
    duplicate of grey shorts of the same cut". When *neither* side has
    a colour signature we fall back to phash-only behaviour for
    backwards compatibility with rows that pre-date the colour-sig
    backfill.
    """
    if sha_a and sha_b and sha_a == sha_b:
        return True
    if not phash_a or not phash_b:
        return False
    if hamming_distance(phash_a, phash_b) > hamming_threshold:
        return False
    # Shape says "match"; gate on colour if we have it.
    if color_a and color_b:
        return color_distance(color_a, color_b) <= color_threshold
    return True
