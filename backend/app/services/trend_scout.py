"""Trend-Scout / Fashion-Scout agent.

Runs on a schedule (daily at 07:00 UTC) and generates short editorial cards
for the home feed and the Stylist side panel.

Phase R extends the schema so the stylist page can render a richer
"news-flash" feed with optional media:

    {
      "bucket": "runway" | "street" | "sustainability" | "influencers"
                 | "second_hand" | "recycling" | "news_flash",
      "headline": str,
      "body": str,
      "tag": str,
      "source_name": str | None,
      "source_url": str | None,
      "image_url": str | None,
      "video_url": str | None,
    }

The agent does not yet call out to the live web (keeps things self-contained
and deterministic). It asks Gemini for a plausible, editorial-voice
observation *and* a suggestive source/media citation. When the generator
returns a URL we keep it; otherwise the fields stay null and the UI
gracefully falls back to a gradient tile.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from emergentintegrations.llm.chat import LlmChat, UserMessage

from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Buckets — prompts read like mini editorial briefs.
# ---------------------------------------------------------------------------
BUCKETS: list[dict[str, str]] = [
    {
        "slug": "ss26-runway",
        "label": "Runway",
        "prompt": (
            "Summarise ONE concrete SS26 runway trend worth a closet update."
            " Focus on silhouette, fabric, or signature colour."
        ),
    },
    {
        "slug": "street",
        "label": "Street",
        "prompt": (
            "Name ONE street-style shift that's actually being worn (not"
            " editorial fantasy). Call out the key item and the styling move."
        ),
    },
    {
        "slug": "sustainability",
        "label": "Sustainability",
        "prompt": (
            "Pick ONE emerging sustainability story (resale, swap, materials,"
            " repair, rental) and state the user-facing implication."
        ),
    },
    {
        "slug": "influencers",
        "label": "Influencers",
        "prompt": (
            "Highlight ONE global fashion influencer whose feed is shaping"
            " how people are dressing right now. Name the person, their"
            " signature move, and why it matters."
        ),
    },
    {
        "slug": "second_hand",
        "label": "Second-hand",
        "prompt": (
            "Spotlight ONE concrete second-hand / vintage marketplace trend"
            " (platform, category, buyer behaviour). Make it actionable."
        ),
    },
    {
        "slug": "recycling",
        "label": "Recycling",
        "prompt": (
            "Call out ONE innovative clothing-recycling or repair idea that"
            " a home wardrobe could realistically adopt this month."
        ),
    },
    {
        "slug": "news_flash",
        "label": "News Flash",
        "prompt": (
            "Deliver ONE breaking fashion-industry headline worth sharing in"
            " a news-flash ticker (brand move, collaboration, regulation,"
            " launch). Be factual-sounding and editorial."
        ),
    },
]


SYSTEM_PROMPT = (
    "You are DressApp's Fashion-Scout — a sharp, concise fashion journalist."
    " Write for a reader who already dresses well and wants ONE actionable"
    " insight per card. Voice: editorial, confident, never salesy."
    "\n\nOutput contract: return ONLY a JSON object with these keys:"
    ' {"headline": string (<= 8 words),'
    ' "body": string (1-2 sentences, <= 220 chars),'
    ' "tag": string (short all-caps category tag),'
    ' "source_name": string (publication or outlet the insight could be'
    ' attributed to, e.g., "Vogue Runway", "Business of Fashion", "Hypebeast",'
    ' or the influencer\'s handle),'
    ' "source_url": string (a plausible landing URL on that source — https'
    ' only; may be a best-guess homepage if a deep link is unknown),'
    ' "image_url": string (direct https link to a free-to-use stock image,'
    ' OR null if uncertain — never fabricate a private CDN URL),'
    ' "video_url": string (optional direct https link to a short public video,'
    ' else null)}. No markdown, no prose outside JSON, no trailing commentary.'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:  # noqa: BLE001
            pass
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(raw[first : last + 1])
        except Exception:  # noqa: BLE001
            pass
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def _clean_url(value: Any) -> str | None:
    """Keep only https URLs and strip obvious fabrications."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    if not v.lower().startswith(("http://", "https://")):
        return None
    # Normalize to https to avoid mixed-content warnings in the browser.
    if v.lower().startswith("http://"):
        v = "https://" + v[len("http://") :]
    # Reject obviously-fake hosts (private or example.com) to keep the UI honest.
    lowered = v.lower()
    if "example.com" in lowered or "localhost" in lowered:
        return None
    return v[:300]


async def _generate_one(bucket: dict[str, str]) -> dict[str, Any] | None:
    api_key = settings.gemini_chat_key
    if not api_key:
        raise RuntimeError(
            "No Gemini chat key set (GEMINI_API_KEY / EMERGENT_LLM_KEY) — "
            "cannot run Trend-Scout"
        )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"fashionscout-{bucket['slug']}-{uuid.uuid4().hex[:8]}",
        system_message=SYSTEM_PROMPT,
    )
    # Phase: Flash is fast/cheap and ample for trend scouting (per user
    # preference — Pro reserved for the Stylist).
    chat.with_model(
        settings.DEFAULT_STYLIST_PROVIDER, "gemini-2.5-flash"
    )
    try:
        raw = await chat.send_message(UserMessage(text=bucket["prompt"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fashion-Scout LLM call failed for %s: %s", bucket["slug"], exc)
        return None
    parsed = _extract_json(raw or "")
    if not parsed.get("headline") or not parsed.get("body"):
        logger.warning(
            "Fashion-Scout returned unparseable payload for %s: %s",
            bucket["slug"],
            (raw or "")[:200],
        )
        return None
    return {
        "headline": str(parsed["headline"])[:140],
        "body": str(parsed["body"])[:400],
        "tag": (parsed.get("tag") or bucket["label"]).upper()[:40],
        "source_name": (parsed.get("source_name") or "")[:80] or None,
        "source_url": _clean_url(parsed.get("source_url")),
        "image_url": _clean_url(parsed.get("image_url")),
        "video_url": _clean_url(parsed.get("video_url")),
    }


async def _already_today(bucket_slug: str) -> bool:
    db = get_db()
    today = date.today().isoformat()
    existing = await db.trend_reports.find_one(
        {"bucket": bucket_slug, "date": today, "language": {"$in": [None, "en"]}}
    )
    return bool(existing)


async def run_trend_scout(*, force: bool = False) -> dict[str, Any]:
    """Generate and persist today's fashion-scout cards. Safe to call on demand."""
    db = get_db()
    today = date.today().isoformat()
    results: list[dict[str, Any]] = []
    skipped: list[str] = []
    for bucket in BUCKETS:
        if not force and await _already_today(bucket["slug"]):
            skipped.append(bucket["slug"])
            continue
        card = await _generate_one(bucket)
        if not card:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "bucket": bucket["slug"],
            "bucket_label": bucket["label"],
            "date": today,
            "language": "en",
            "country_code": None,
            "headline": card["headline"],
            "body": card["body"],
            "tag": card["tag"],
            "source_name": card.get("source_name"),
            "source_url": card.get("source_url"),
            "image_url": card.get("image_url"),
            "video_url": card.get("video_url"),
            "model": settings.DEFAULT_STYLIST_MODEL,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.trend_reports.replace_one(
            {"bucket": bucket["slug"], "date": today, "language": "en"}, doc, upsert=True
        )
        results.append(doc)
    logger.info(
        "Fashion-Scout run complete: generated=%d, skipped=%d",
        len(results),
        len(skipped),
    )
    return {
        "generated": [{k: v for k, v in r.items() if k != "_id"} for r in results],
        "skipped": skipped,
        "date": today,
    }


async def latest_trend_cards(limit_per_bucket: int = 1) -> list[dict[str, Any]]:
    """Return the most recent English card for each bucket, newest first (legacy feed)."""
    db = get_db()
    out: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        cursor = (
            db.trend_reports.find(
                {"bucket": bucket["slug"], "language": {"$in": [None, "en"]}},
                {"_id": 0},
            )
            .sort("date", -1)
            .limit(limit_per_bucket)
        )
        async for doc in cursor:
            out.append(doc)
    return out


async def fashion_scout_feed(
    limit: int = 10,
    *,
    language: str | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    """Newest-first flat feed for the Stylist side panel.

    When `language` is supplied and differs from ``en`` we look up cached
    translated cards for that (bucket, date, language) triplet, and when
    none are present we translate the English canon on demand (storing the
    result so the next reader is instant). `country` tailors source picks
    and tone when translating.
    """
    db = get_db()
    language = (language or "en").lower()
    limit = max(1, min(limit, 50))

    # Pull newest-first English canon for the requested limit.
    cursor = (
        db.trend_reports.find({"language": {"$in": [None, "en"]}}, {"_id": 0})
        .sort([("date", -1), ("created_at", -1)])
        .limit(limit)
    )
    canon = [doc async for doc in cursor]
    if language == "en" or not canon:
        return canon

    out: list[dict[str, Any]] = []
    for card in canon:
        cached = await db.trend_reports.find_one(
            {
                "origin_id": card["id"],
                "language": language,
                **({"country_code": country.upper()} if country else {}),
            },
            {"_id": 0},
        )
        if cached:
            out.append(cached)
            continue
        translated = await _translate_card(
            card, language=language, country=country
        )
        if translated:
            await db.trend_reports.insert_one({**translated, "_origin": card["id"]})
            out.append({k: v for k, v in translated.items() if k != "_id"})
        else:
            out.append(card)
    return out


async def _translate_card(
    card: dict[str, Any],
    *,
    language: str,
    country: str | None,
) -> dict[str, Any] | None:
    """Translate a canonical English card into the target language.

    We ask Gemini Flash for a structured translation plus *regionalization*
    — so an Israeli reader sees culturally-relevant source picks and idiom.
    Returns a fresh document with a new id so the cached list operates on
    stable primary keys.
    """
    api_key = settings.gemini_chat_key
    if not api_key:
        return None
    lang_name = {
        "en": "English",
        "he": "Hebrew",
        "ar": "Arabic",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
        "zh": "Chinese",
        "ja": "Japanese",
        "hi": "Hindi",
    }.get(language, "English")
    country_clause = (
        f" The reader is in country code {country.upper()}. Tune the tone,"
        f" examples and — where the original was generic — the source_name"
        f" / source_url to an outlet a {country.upper()} reader would"
        f" actually recognise."
        if country
        else ""
    )
    system_prompt = (
        f"You localise DressApp fashion-scout cards into {lang_name}. Keep"
        " the editorial voice crisp and factual. Preserve factual claims;"
        " only adapt idioms and examples."
        f"{country_clause}"
        " Return ONLY a JSON object with the keys: headline, body, tag,"
        " source_name, source_url, image_url, video_url."
        " Preserve URLs verbatim (do not translate them). Tag remains"
        " short, uppercase, in the target language."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"scoutxl-{uuid.uuid4().hex[:8]}",
        system_message=system_prompt,
    )
    chat.with_model(settings.DEFAULT_STYLIST_PROVIDER, "gemini-2.5-flash")
    try:
        raw = await chat.send_message(
            UserMessage(
                text=json.dumps(
                    {
                        "headline": card.get("headline"),
                        "body": card.get("body"),
                        "tag": card.get("tag"),
                        "source_name": card.get("source_name"),
                        "source_url": card.get("source_url"),
                        "image_url": card.get("image_url"),
                        "video_url": card.get("video_url"),
                    },
                    ensure_ascii=False,
                )
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Translate scout card failed (%s -> %s): %s",
            card.get("id"),
            language,
            exc,
        )
        return None
    parsed = _extract_json(raw or "")
    if not parsed.get("headline") or not parsed.get("body"):
        return None
    return {
        "id": str(uuid.uuid4()),
        "origin_id": card["id"],
        "bucket": card["bucket"],
        "bucket_label": card.get("bucket_label"),
        "date": card.get("date"),
        "headline": str(parsed["headline"])[:140],
        "body": str(parsed["body"])[:400],
        "tag": (parsed.get("tag") or card.get("tag") or "").upper()[:40],
        "source_name": (parsed.get("source_name") or card.get("source_name"))[:80]
        if parsed.get("source_name") or card.get("source_name")
        else None,
        "source_url": _clean_url(parsed.get("source_url"))
        or card.get("source_url"),
        "image_url": _clean_url(parsed.get("image_url")) or card.get("image_url"),
        "video_url": _clean_url(parsed.get("video_url")) or card.get("video_url"),
        "language": language,
        "country_code": (country or "").upper() or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
