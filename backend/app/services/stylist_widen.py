"""Widen-the-search orchestrator for the Stylist (Phase S).

When the Stylist's primary advice mentions a garment that the user does
*not* already own — or when the user explicitly toggles "Search wider"
on — this module:

  1. **Detects which categories** the recommendation referenced
     (top / bottom / shoes / outerwear / accessory / dress).
  2. **Marketplace search** for those categories on the user's listings.
  3. **Fashion Scout** trend cards relevant to the brief (style
     inspiration, current season picks).
  4. **Nano Banana visualization** when the user asked to be "shown" /
     "displayed" / "pictured" something OR when both the closet AND
     marketplace turned up empty for that slot.

Returned dict matches the new ``StylistEnrichment`` schema. The Stylist
endpoint merges it into the ``StylistAdvice`` payload.

Semantics intentionally lenient: every step is wrapped so a single
failure (e.g. trend feed empty, Nano Banana over quota) cannot 500 the
parent endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.services import marketplace_search, trend_scout
from app.services.gemini_image_service import gemini_image_service

logger = logging.getLogger(__name__)


# ─── tunables ────────────────────────────────────────────────
MAX_VISUALIZATIONS = 2   # cap to keep latency + token cost bounded
MAX_MARKETPLACE = 6
MAX_TREND_CARDS = 4

# Triggers that escalate to Nano Banana visualisation. Includes Hebrew
# equivalents because the Stylist runs bilingual.
_VISUALIZE_RE = re.compile(
    r"\b(show|display|draw|picture|render|visuali[zs]e|illustrate|example)\b"
    r"|(תראי|הראי|הצגי|תציירי|דוגמ)",
    re.IGNORECASE | re.UNICODE,
)

# Light category lexicon (English + Hebrew) used to *infer* which slots
# the Stylist's advice references.
_CATEGORY_LEXICON: dict[str, list[str]] = {
    "shoes": ["shoe", "shoes", "sneaker", "boot", "heel", "loafer", "sandal", "trainer", "נעל", "סנדל", "מגף"],
    "top": ["shirt", "t-shirt", "tshirt", "blouse", "top", "sweater", "knit", "polo", "hoodie", "חולצה", "סוודר", "גופייה"],
    "bottom": ["pant", "pants", "trouser", "jean", "jeans", "short", "shorts", "skirt", "מכנס", "גינס", "חצאית"],
    "dress": ["dress", "gown", "שמלה"],
    "outerwear": ["jacket", "coat", "blazer", "parka", "מעיל", "ז'קט", "בלייזר"],
    "accessory": ["belt", "watch", "scarf", "bracelet", "necklace", "earring", "חגורה", "שעון", "צעיף"],
    "bag": ["bag", "handbag", "clutch", "backpack", "purse", "תיק", "תרמיל"],
    "headwear": ["hat", "cap", "beanie", "כובע"],
}


# ─── public ──────────────────────────────────────────────────
async def widen_stylist_response(
    *,
    user: dict[str, Any],
    user_text: str,
    advice: dict[str, Any],
    closet_summary: dict[str, Any] | None,
    user_requested_widen: bool = False,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return enrichment dict to merge into the StylistAdvice payload.

    Always returns a dict; never raises.
    """
    constraints = constraints or {}
    out: dict[str, Any] = {
        "marketplace_suggestions": [],
        "fashion_scout_picks": [],
        "generated_examples": [],
        "widened_for": [],
    }
    try:
        gap_categories = _infer_gap_categories(
            advice=advice,
            closet_summary=closet_summary,
            user_text=user_text,
        )
        # User-requested widen overrides closet check — search even when
        # closet has the item, because the user explicitly asked.
        if user_requested_widen and not gap_categories:
            gap_categories = _all_referenced_categories(advice, user_text)
        if not gap_categories:
            return out
        out["widened_for"] = sorted(gap_categories)

        # Run the three enrichment branches in parallel.
        market_task = _gather_marketplace(user, gap_categories, user_text, constraints)
        scout_task = _gather_scout(user)
        results = await asyncio.gather(market_task, scout_task, return_exceptions=True)
        market = results[0] if not isinstance(results[0], Exception) else []
        scout = results[1] if not isinstance(results[1], Exception) else []
        out["marketplace_suggestions"] = market[:MAX_MARKETPLACE]
        out["fashion_scout_picks"] = scout[:MAX_TREND_CARDS]

        # Nano Banana visualization gate (choice 2d):
        # explicit "show me" trigger OR (closet empty AND marketplace empty).
        explicit = bool(_VISUALIZE_RE.search(user_text or ""))
        if explicit or (not market and not _closet_has_any_of(closet_summary, gap_categories)):
            out["generated_examples"] = await _gather_visualizations(
                advice=advice,
                user_text=user_text,
                gap_categories=gap_categories,
                user=user,
                explicit_trigger=explicit,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("widen_stylist_response soft-failed: %s", repr(exc)[:240])
    return out


# ─── inference helpers ──────────────────────────────────────
def _infer_gap_categories(
    *, advice: dict[str, Any], closet_summary: dict[str, Any] | None, user_text: str,
) -> set[str]:
    """Categories the advice mentions that the closet does NOT cover."""
    referenced = _all_referenced_categories(advice, user_text)
    if not referenced:
        return set()
    have_in_closet = _closet_categories(closet_summary)
    return referenced - have_in_closet


def _all_referenced_categories(advice: dict[str, Any], user_text: str) -> set[str]:
    haystack_parts: list[str] = []
    haystack_parts.append(user_text or "")
    haystack_parts.append(advice.get("reasoning_summary") or "")
    haystack_parts.append(advice.get("transcript") or "")
    haystack_parts.append(advice.get("spoken_reply") or "")
    for r in advice.get("outfit_recommendations") or []:
        if isinstance(r, dict):
            haystack_parts.append(r.get("description") or "")
            haystack_parts.append(r.get("why") or "")
    for s in advice.get("shopping_suggestions") or []:
        haystack_parts.append(str(s))
    haystack = " ".join(p.lower() for p in haystack_parts)
    found: set[str] = set()
    for cat, words in _CATEGORY_LEXICON.items():
        for w in words:
            if w in haystack:
                found.add(cat)
                break
    return found


def _closet_categories(closet_summary: dict[str, Any] | None) -> set[str]:
    if not isinstance(closet_summary, dict):
        return set()
    items = closet_summary.get("items") or []
    out: set[str] = set()
    for it in items:
        cat = (it.get("category") or "").lower()
        if not cat:
            continue
        if cat in {"shoe", "footwear", "sneaker", "boot", "heel"}:
            out.add("shoes")
        elif cat in {"shirt", "tshirt", "top", "blouse", "sweater", "knit", "polo"}:
            out.add("top")
        elif cat in {"pants", "trousers", "jeans", "shorts", "skirt", "bottom"}:
            out.add("bottom")
        elif cat == "dress":
            out.add("dress")
        elif cat in {"jacket", "coat", "blazer", "outerwear"}:
            out.add("outerwear")
        elif cat in {"belt", "watch", "scarf", "accessory"}:
            out.add("accessory")
        elif cat in {"bag", "handbag", "backpack"}:
            out.add("bag")
        elif cat in {"hat", "cap", "headwear"}:
            out.add("headwear")
    return out


def _closet_has_any_of(closet_summary: dict[str, Any] | None, cats: set[str]) -> bool:
    return bool(_closet_categories(closet_summary) & cats)


# ─── enrichment branches ────────────────────────────────────
async def _gather_marketplace(
    user: dict[str, Any],
    cats: set[str],
    user_text: str,
    constraints: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps = [{"role": c} for c in cats]
    return await marketplace_search.suggest_for_gaps(
        user=user, gaps=gaps, brief=user_text, constraints=constraints, per_gap=2,
    )


async def _gather_scout(user: dict[str, Any]) -> list[dict[str, Any]]:
    lang = (user.get("preferred_language") or "en").lower()
    addr = user.get("address") or {}
    country = (addr.get("country") or "").upper() or None
    feed = await trend_scout.fashion_scout_feed(limit=6, language=lang, country=country)
    return [
        {
            "id": c.get("id"),
            "title": c.get("title") or c.get("trend_title") or "Trend",
            "summary": c.get("summary") or c.get("trend_summary") or "",
            "image_url": c.get("image_url") or c.get("hero_image_url"),
            "source_name": c.get("source_name"),
            "source_url": c.get("source_url"),
            "bucket": c.get("bucket") or c.get("bucket_slug"),
        }
        for c in feed
    ]


async def _gather_visualizations(
    *,
    advice: dict[str, Any],
    user_text: str,
    gap_categories: set[str],
    user: dict[str, Any],
    explicit_trigger: bool,  # noqa: ARG001 — reserved for richer prompts
) -> list[dict[str, Any]]:
    if gemini_image_service is None:
        return []
    # Pick at most MAX_VISUALIZATIONS categories — prefer shoes / dress
    # / outerwear since those visually anchor an outfit.
    priority = ["shoes", "dress", "outerwear", "top", "bottom", "accessory", "bag"]
    targets = [c for c in priority if c in gap_categories][:MAX_VISUALIZATIONS]
    if not targets:
        targets = list(gap_categories)[:MAX_VISUALIZATIONS]

    sex = (user.get("sex") or "").lower()
    style_words = (user.get("style_profile") or {}).get("aesthetics") or []
    style_blurb = ", ".join(str(s) for s in style_words[:3])

    async def _one(cat: str) -> dict[str, Any] | None:
        prompt = _build_viz_prompt(
            category=cat,
            user_text=user_text,
            sex=sex,
            style_blurb=style_blurb,
            advice=advice,
        )
        try:
            out = await gemini_image_service.generate(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.info("Nano Banana viz [%s] failed: %s", cat, repr(exc)[:160])
            return None
        if not out or not out.get("image_b64"):
            return None
        return {
            "category": cat,
            "prompt": prompt[:240],
            "image_data_url": f"data:{out.get('mime_type', 'image/png')};base64,{out['image_b64']}",
            "caption": _viz_caption(cat, advice),
        }

    sem = asyncio.Semaphore(2)

    async def _gated(cat: str) -> dict[str, Any] | None:
        async with sem:
            return await _one(cat)

    results = await asyncio.gather(*[_gated(c) for c in targets], return_exceptions=False)
    return [r for r in results if r]


def _build_viz_prompt(
    *, category: str, user_text: str, sex: str, style_blurb: str, advice: dict[str, Any]
) -> str:
    descriptor_bits: list[str] = []
    rec_bits: list[str] = []
    for r in advice.get("outfit_recommendations") or []:
        if isinstance(r, dict):
            d = r.get("description") or ""
            if d:
                rec_bits.append(d)
    if rec_bits:
        descriptor_bits.append(" ".join(rec_bits)[:240])
    if user_text:
        descriptor_bits.append(user_text[:160])
    if style_blurb:
        descriptor_bits.append(f"Style: {style_blurb}")
    if sex:
        descriptor_bits.append(f"Wearer: {sex}")
    descriptor = ". ".join(descriptor_bits) or ""
    return (
        f"Editorial product photograph of a single {category}. {descriptor}. "
        "Studio lighting, plain off-white backdrop, centered composition, "
        "sharp focus, photorealistic, clean fabric texture, no people, "
        "no mannequin body parts, no text, no logos, no watermarks."
    )[:1000]


def _viz_caption(category: str, advice: dict[str, Any]) -> str:
    rec = (advice.get("outfit_recommendations") or [{}])[0]
    desc = rec.get("description") if isinstance(rec, dict) else None
    if desc:
        return f"Suggested {category}: {desc[:80]}"
    return f"Suggested {category}"
