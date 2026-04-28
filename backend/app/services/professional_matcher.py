"""Heuristic Professional pool referral.

Per user choice **4a** the Stylist surfaces a single pro card *only* when
the brief or composed outfit shows a clear signal that human help is
needed — tailoring, repair, dry cleaning, formal-occasion styling, etc.
Always-on pro cards are deferred to a later phase.

Trigger pipeline:

    brief + outfit signals  →  (signal_keywords, profession)  →  query
    /professionals directory filtered by profession + region + language

Heuristic-only (no LLM round-trip). Latency budget: ~5 ms.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.db.database import get_db

logger = logging.getLogger(__name__)


# ─── trigger lexicon ────────────────────────────────────────
# Each entry maps a regex (ASCII + Hebrew) to a (profession, why) pair.
# Profession strings match the values stored under
# ``user.professional.profession`` by the existing /professionals
# directory: tailor, dry_cleaner, stylist, cobbler, jeweller, etc.
_TRIGGERS: list[tuple[re.Pattern[str], str, str]] = [
    # tailoring / alterations
    (re.compile(r"\b(tailor(ing)?|alter(ation)?s?|hem|fit(ting)?|too\s+(big|small|loose|tight))\b", re.I),
     "tailor", "Brief mentions fit/alteration — a tailor can dial it in."),
    (re.compile(r"(תפירה|תיקון\s*בגד|הצרה|חייט)", re.I),
     "tailor", "Brief mentions tailoring — a tailor can dial it in."),
    # repair / mending
    (re.compile(r"\b(repair|rip(ped)?|tear|stitch|mend|missing\s+button)\b", re.I),
     "tailor", "Repair signal detected — a tailor or seamstress can fix this."),
    # dry cleaning / stain
    (re.compile(r"\b(dry[\s-]?clean(ing)?|stain|spotted|smelly)\b", re.I),
     "dry_cleaner", "Cleaning signal — a dry cleaner can refresh it."),
    (re.compile(r"(ניקוי\s*יבש|כתם)", re.I),
     "dry_cleaner", "Cleaning signal — a dry cleaner can refresh it."),
    # special occasions
    (re.compile(r"\b(wedding|black[-\s]?tie|gala|funeral|interview|red[-\s]?carpet|prom)\b", re.I),
     "stylist", "Big occasion — a personal stylist can pull together a polished look."),
    (re.compile(r"(חתונה|לוויה|אירוע\s*חגיגי|ראיון\s*עבודה)", re.I),
     "stylist", "Big occasion — a personal stylist can pull together a polished look."),
    # shoes / cobbler
    (re.compile(r"\b(re[-\s]?sole|polish\s*shoes?|cobbler|shoe[-\s]?repair)\b", re.I),
     "cobbler", "Footwear repair signal — a cobbler can sort it."),
    # jewellery resize / repair
    (re.compile(r"\b(re[-\s]?size\s+ring|jewell?ery\s+(repair|resize)|broken\s+chain)\b", re.I),
     "jeweller", "Jewellery work needed."),
]


# ─── public API ─────────────────────────────────────────────
async def maybe_suggest(
    *,
    brief: str,
    constraints: dict[str, Any],
    slots: list[dict[str, Any]],  # noqa: ARG001 — reserved for future signals
    candidates: list[dict[str, Any]],  # noqa: ARG001 — reserved for future signals
    user: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a single ProfessionalSuggestion dict or None."""
    triggers = _detect_triggers(brief, constraints)
    if not triggers:
        return None
    profession = triggers[0][0]
    why = triggers[0][1]
    keywords = [t[2] for t in triggers]
    pro = await _find_best_pro(profession=profession, user=user)
    if not pro:
        return None
    return {
        "professional_id": pro.get("id") or "",
        "display_name": pro.get("display_name")
        or " ".join([pro.get("first_name") or "", pro.get("last_name") or ""]).strip()
        or "Fashion pro",
        "profession": profession,
        "avatar_url": pro.get("avatar_url"),
        "location": _format_location(pro),
        "why_suggested": why,
        "triggered_by": keywords,
    }


# ─── internals ──────────────────────────────────────────────
def _detect_triggers(
    brief: str, constraints: dict[str, Any],
) -> list[tuple[str, str, str]]:
    """Returns list of (profession, why, matched_text) in order of strength."""
    haystack = brief or ""
    for v in (constraints or {}).values():
        if isinstance(v, str):
            haystack += " " + v
        elif isinstance(v, list):
            haystack += " " + " ".join(str(x) for x in v)
    hits: list[tuple[str, str, str]] = []
    for pattern, profession, why in _TRIGGERS:
        m = pattern.search(haystack)
        if m:
            hits.append((profession, why, m.group(0)))
    return hits


async def _find_best_pro(
    *, profession: str, user: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Query the /professionals directory for a match.

    Filters used (in order of preference):
      1. Same profession
      2. (Optional) Same country/region as the requesting user
      3. ``professional.public=true`` (only public-listed pros)
      4. Highest ``professional.rating`` if present, else newest first
    """
    db = get_db()
    user = user or {}
    base_query: dict[str, Any] = {
        "professional.profession": profession,
        "professional.public": True,
    }

    # Region/country preference (soft). We try region-matched first,
    # then fall back to global if nothing local is available.
    region = (user.get("country") or user.get("region") or "").strip()
    candidate_queries = []
    if region:
        candidate_queries.append({**base_query, "country": region})
    candidate_queries.append(base_query)

    for q in candidate_queries:
        cursor = (
            db.users.find(q, {"_id": 0})
            .sort([("professional.rating", -1), ("created_at", -1)])
            .limit(1)
        )
        async for doc in cursor:
            return doc
    return None


def _format_location(pro: dict[str, Any]) -> str | None:
    bits = [pro.get("city"), pro.get("region"), pro.get("country")]
    bits = [b for b in bits if b]
    return ", ".join(bits) if bits else None
