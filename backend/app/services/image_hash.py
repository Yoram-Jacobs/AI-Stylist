"""
Phase Z2 — perceptual image hashing helpers.

Used by /closet/preflight to detect duplicate uploads even when:
  * the existing item's "original_image_url" was never stored (legacy
    items keep only a thumbnail / segmented preview);
  * the user re-exports their photo at a different JPEG quality;
  * the user takes a slightly different shot of the same garment
    (similar angle, similar lighting).

Implementation: a 64-bit average-hash (aHash). Cheap (~3 ms per image
on a typical pod), no extra dependencies — only Pillow + numpy, both
already in requirements.txt. Hamming distance ≤ 6 bits ≈ "the same
garment in a similar pose".

We intentionally avoid pHash (DCT-based) here. aHash is more
forgiving with subtle colour shifts (lighting changes between two
shots of the same garment) which is the workflow we care about, and
it's significantly faster — important for the on-the-fly backfill
inside /preflight which may need to hash 50-200 thumbnails in a single
request.
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
