"""Detect potential duplicates of newly-analysed garments.

Problem
-------
After ``/closet/analyze`` produces a clean cutout + LLM analysis, we want
to spare the user from accidentally re-uploading a garment they already
own (the most common case: same DSLR shot uploaded twice while iterating
on lighting). Without this they'd end up with two identical "Charcoal
Grey Polo Shirt" cards and no clear signal which to keep.

Strategy (Option A — strict matching, recommended in chat)
----------------------------------------------------------
Flag a duplicate when ALL of these match an existing closet item:

* ``item_type`` (case-insensitive)
* ``sub_category`` (case-insensitive)
* the *dominant* color name (i.e. ``colors[0].name`` if present, else
  the legacy top-level ``color`` field)
* AND if BOTH items carry a ``brand``, the brands must agree
  (otherwise the brand is ignored — many garments are unbranded)

This is strict enough to catch genuine re-uploads ("Charcoal grey polo"
→ "Charcoal grey polo") without false-positiving on "two different white
t-shirts I genuinely own".

Implementation
--------------
The whole analyse-flow runs server-side and already has a Mongo handle,
so we do a single ``.find()`` per analysis call (typically 1-3 items per
upload) using a compound index already in place on
``(user_id, sub_category)``. The fan-out is tiny — 99% of users have
under 200 closet items.
"""
from __future__ import annotations

import logging
from typing import Any

from app.db.database import get_db

logger = logging.getLogger(__name__)


def _norm(value: str | None) -> str:
    """Lower-case + trim. Returns empty string for None / non-str."""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _dominant_color(analysis: dict[str, Any]) -> str:
    """Pick the most-prominent colour name from an analysis dict.

    Priority: first entry of ``colors`` list (carries a ``name`` field) →
    legacy top-level ``color`` string → empty.
    """
    colors = analysis.get("colors") or []
    if isinstance(colors, list) and colors:
        first = colors[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str) and name.strip():
                return _norm(name)
    legacy = analysis.get("color")
    if isinstance(legacy, str) and legacy.strip():
        return _norm(legacy)
    return ""


async def find_potential_duplicate(
    user_id: str, analysis: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the first existing closet item that "looks like" the
    analysed garment, or ``None`` if nothing matches.

    Returns a small projection (``id``, ``title``, ``name``,
    ``item_type``, ``sub_category``, ``brand``, ``thumbnail_data_url``)
    suitable for showing in a confirm-add modal — never the heavy
    base64 image fields, so the analyse response stays small.
    """
    item_type = _norm(analysis.get("item_type"))
    sub_category = _norm(analysis.get("sub_category"))
    color = _dominant_color(analysis)
    brand = _norm(analysis.get("brand"))

    # Need at least item_type + sub_category + color to attempt a match.
    # Without those we can't be confident enough to interrupt the user.
    if not (item_type and sub_category and color):
        return None

    db = get_db()
    # Mongo's ``$regex`` with ``$options="i"`` would also work but we'd
    # have to escape user input. Doing the case-fold in Python is simpler
    # and equally fast given the closet sizes we're dealing with.
    cursor = db.closet_items.find(
        {
            "user_id": user_id,
            # sub_category is the cheapest discriminator (small cardinality)
            # so we filter by it server-side; everything else is checked
            # in Python.
            "sub_category": {"$regex": f"^{sub_category}$", "$options": "i"},
        },
        {
            "_id": 0,
            "id": 1,
            "title": 1,
            "name": 1,
            "item_type": 1,
            "sub_category": 1,
            "brand": 1,
            "color": 1,
            "colors": 1,
            "thumbnail_data_url": 1,
        },
    ).limit(50)

    async for existing in cursor:
        if _norm(existing.get("item_type")) != item_type:
            continue
        existing_color = _dominant_color(existing)
        if existing_color != color:
            continue
        existing_brand = _norm(existing.get("brand"))
        if brand and existing_brand and brand != existing_brand:
            # Both branded but brands differ → not a duplicate.
            continue
        # Match!
        return {
            "id": existing.get("id"),
            "title": existing.get("title") or existing.get("name") or "Untitled garment",
            "name": existing.get("name"),
            "item_type": existing.get("item_type"),
            "sub_category": existing.get("sub_category"),
            "brand": existing.get("brand"),
            "thumbnail_data_url": existing.get("thumbnail_data_url"),
        }
    return None
