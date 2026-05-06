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

import asyncio
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# Personalization (Phase TS-2)
#
# Until the real web-scouring integration lands (Tavily / Perplexity / etc,
# tracked as a future tier-pricing milestone), the trend pool is
# generated by an LLM and stored in ``trend_reports``. We can still
# give the user a meaningfully better feed by **ranking the same pool
# against their demographics** at read time — gender, occupation,
# professional profile, and country.
#
# The ranker is intentionally simple: a deterministic keyword-overlap
# score with a few content-aware boosts. This avoids another LLM call
# on every read (cost + latency) and keeps the behaviour debuggable.
# When the live web search ships, the same ranker will simply operate
# on a richer, real-content pool.
# ---------------------------------------------------------------------------
_BUCKET_AFFINITY: dict[str, dict[str, float]] = {
    # Bucket → keyword → weight. Boosts the bucket when the user's
    # keyword set hints at an interest in that subject. Weights kept
    # small (≤ 2.0) so they nudge ranking rather than dominate it.
    "ss26-runway": {
        "designer": 2.0, "stylist": 1.5, "fashion": 1.5, "model": 1.5,
        "editor": 1.0, "creative": 1.0, "luxury": 1.0,
    },
    "street": {
        "student": 1.5, "artist": 1.0, "musician": 1.0, "casual": 1.0,
        "skater": 2.0, "athlete": 1.0,
    },
    "sustainability": {
        "engineer": 1.0, "scientist": 1.5, "teacher": 1.0,
        "sustainability": 2.0, "climate": 2.0, "activist": 2.0,
    },
    "influencers": {
        "marketing": 1.5, "social": 1.5, "content": 1.5, "creator": 2.0,
        "influencer": 2.0, "brand": 1.0,
    },
    "second_hand": {
        "thrift": 2.0, "vintage": 2.0, "student": 1.5, "budget": 1.0,
    },
    "recycling": {
        "designer": 1.0, "engineer": 1.0, "tailor": 1.5, "diy": 1.5,
    },
    "news_flash": {},  # neutral
}

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(_TOKEN_RE.findall(text.lower()))


def _user_keyword_set(user: dict[str, Any]) -> set[str]:
    """Build the user's relevance keyword set from their profile."""
    parts: list[str] = []
    for key in ("occupation", "first_name", "last_name", "display_name"):
        v = user.get(key)
        if isinstance(v, str):
            parts.append(v)
    sex = user.get("sex")
    if isinstance(sex, str):
        # Map sex → likely fashion-feed keywords. Cards rarely tag
        # gender explicitly so we look for the english noun forms.
        if sex == "female":
            parts.append("women womens woman")
        elif sex == "male":
            parts.append("men mens man")
    prof = user.get("professional") or {}
    if isinstance(prof, dict):
        if prof.get("profession"):
            parts.append(str(prof["profession"]))
        biz = prof.get("business") or {}
        if isinstance(biz, dict) and biz.get("description"):
            parts.append(str(biz["description"])[:200])
    home = user.get("home_location") or {}
    addr = user.get("address") or {}
    for source in (home, addr):
        if isinstance(source, dict):
            for k in ("city", "region", "country", "country_code"):
                v = source.get(k)
                if isinstance(v, str):
                    parts.append(v)
    return _tokens(" ".join(parts))


def _country_codes(user: dict[str, Any]) -> set[str]:
    """Best-effort country code set for the viewer (upper-case)."""
    out: set[str] = set()
    for source_key in ("home_location", "address"):
        source = user.get(source_key) or {}
        if isinstance(source, dict):
            for k in ("country_code", "country"):
                v = source.get(k)
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().upper())
    return out


def _opposite_gender_penalty(card: dict[str, Any], sex: str | None) -> float:
    """Soft-penalise cards that explicitly target the opposite gender.

    Hard filtering is deliberately avoided — fashion stories often
    apply across genders even when the headline mentions one — so we
    just tilt the ranking down (-2) rather than dropping the card.
    """
    if not sex:
        return 0.0
    text = f"{card.get('headline', '')} {card.get('body', '')}".lower()
    if sex == "female" and (" men's " in f" {text} " or "menswear" in text):
        return -2.0
    if sex == "male" and (" women's " in f" {text} " or "womenswear" in text):
        return -2.0
    return 0.0


def rank_cards_for_user(
    cards: list[dict[str, Any]],
    user: dict[str, Any],
) -> list[dict[str, Any]]:
    """Sort ``cards`` (highest relevance first) for the supplied user.

    Scoring:
      * +2 for each user-keyword token that appears in the card text.
      * +0..2 bucket-affinity boost based on user keywords.
      * +3 if the card text mentions a country we associate with the user.
      * -2 soft penalty for cards that explicitly target the opposite gender.
      * Ties broken by recency (``date`` desc, then ``created_at`` desc).
    """
    if not cards:
        return cards
    user_keywords = _user_keyword_set(user)
    user_countries = _country_codes(user)
    sex = user.get("sex") if isinstance(user.get("sex"), str) else None

    def _score(card: dict[str, Any]) -> float:
        text_tokens = _tokens(
            " ".join(
                str(card.get(k, "") or "")
                for k in ("headline", "body", "tag", "source_name")
            )
        )
        score = 0.0
        # 1) Keyword overlap.
        overlap = user_keywords & text_tokens
        score += 2.0 * len(overlap)
        # 2) Bucket affinity from the user's vocabulary.
        affinity = _BUCKET_AFFINITY.get(card.get("bucket") or "", {})
        for kw, weight in affinity.items():
            if kw in user_keywords:
                score += weight
        # 3) Country mention boost.
        if user_countries:
            blob = f"{card.get('body', '')} {card.get('headline', '')}".upper()
            if any(cc and cc in blob for cc in user_countries):
                score += 3.0
        # 4) Opposite-gender soft penalty.
        score += _opposite_gender_penalty(card, sex)
        return score

    def _sort_key(card: dict[str, Any]) -> tuple:
        # Primary: descending score. Secondary: ISO date desc.
        # ``sorted`` is stable, so equal-score cards keep their input
        # ordering — we ensure that ordering is recency-first below.
        return (-_score(card),)

    # Two-pass sort to keep recency stable as the secondary key.
    by_recency = sorted(
        cards,
        key=lambda c: (c.get("date") or "", c.get("created_at") or ""),
        reverse=True,
    )
    return sorted(by_recency, key=_sort_key)


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


_REFRESH_LOCK: asyncio.Lock | None = None
_LAST_AUTO_REFRESH: datetime | None = None


def _stale_threshold() -> int:
    """Hours after which `/trends/latest` reads opportunistically
    schedule a background refresh. Never fewer than 1 hour to keep the
    refresh fire-rate sane even if mis-configured.
    """
    try:
        return max(1, int(getattr(settings, "TREND_SCOUT_STALE_AFTER_HOURS", 24) or 24))
    except (TypeError, ValueError):
        return 24


async def _maybe_background_refresh(cards: list[dict[str, Any]]) -> None:
    """If the newest card is older than the configured stale window,
    fire a background `run_trend_scout` so the next visit gets fresh
    data. Throttled to at most one auto-refresh per stale window to
    avoid hammering the LLM on a busy home page.

    NOTE: we look at ``created_at`` (a real ISO timestamp), not
    ``date`` (a YYYY-MM-DD string) — ``date`` resolution would force a
    refresh as soon as the clock crossed midnight UTC even when fresh
    data from 23:59 had just been written.
    """
    global _LAST_AUTO_REFRESH, _REFRESH_LOCK
    if not getattr(settings, "TREND_SCOUT_ENABLED", True):
        return
    threshold = timedelta(hours=_stale_threshold())
    now = datetime.now(timezone.utc)
    if _LAST_AUTO_REFRESH and (now - _LAST_AUTO_REFRESH) < threshold:
        return  # already auto-refreshed within this stale window
    if not cards:
        # Nothing to compare against — let on-startup / cron handle it.
        return
    newest_iso = max(
        (c.get("created_at") or c.get("updated_at") or "") for c in cards
    )
    try:
        newest = datetime.fromisoformat(newest_iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    if (now - newest) < threshold:
        return  # still fresh
    if _REFRESH_LOCK is None:
        _REFRESH_LOCK = asyncio.Lock()
    if _REFRESH_LOCK.locked():
        return  # someone already kicked off a refresh

    async def _go() -> None:
        global _LAST_AUTO_REFRESH
        async with _REFRESH_LOCK:
            try:
                _LAST_AUTO_REFRESH = datetime.now(timezone.utc)
                logger.info(
                    "Trend-Scout auto-refresh kicked off (newest card was %s)",
                    newest.isoformat(),
                )
                await run_trend_scout()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Trend-Scout auto-refresh failed: %s", exc)

    asyncio.create_task(_go())


async def latest_trend_cards(limit_per_bucket: int = 1) -> list[dict[str, Any]]:
    """Return the most recent English card for each bucket, newest first
    (legacy feed). Opportunistically schedules a background refresh
    when the newest card is older than ``TREND_SCOUT_STALE_AFTER_HOURS``.
    """
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
    # Best-effort auto-refresh — never blocks the response.
    try:
        await _maybe_background_refresh(out)
    except Exception:  # noqa: BLE001
        pass
    return out


async def fashion_scout_feed(
    limit: int = 10,
    *,
    language: str | None = None,
    country: str | None = None,
    user: dict[str, Any] | None = None,
    pool_size: int | None = None,
) -> list[dict[str, Any]]:
    """Newest-first flat feed for the Stylist side panel.

    When `language` is supplied and differs from ``en`` we look up cached
    translated cards for that (bucket, date, language) triplet, and when
    none are present we translate the English canon on demand (storing the
    result so the next reader is instant). `country` tailors source picks
    and tone when translating.

    When `user` is supplied we rank the candidate pool by relevance to
    the viewer's demographics (gender / profession / occupation /
    country) before slicing to ``limit``. ``pool_size`` controls how
    many candidate cards we consider before ranking — defaults to
    ``max(limit, 30)`` so even a Home request for 4 cards picks the 4
    *most relevant* ones from a wide pool, not just the 4 newest.
    """
    db = get_db()
    language = (language or "en").lower()
    limit = max(1, min(limit, 50))
    # Pull a wider pool when we're going to re-rank. With no user
    # context we still respect the historical newest-first contract.
    fetch_limit = max(limit, pool_size or (30 if user else limit))
    fetch_limit = min(fetch_limit, 60)

    # Pull newest-first English canon for the requested limit.
    cursor = (
        db.trend_reports.find({"language": {"$in": [None, "en"]}}, {"_id": 0})
        .sort([("date", -1), ("created_at", -1)])
        .limit(fetch_limit)
    )
    canon = [doc async for doc in cursor]
    if not canon:
        return []
    # Re-rank the pool against the viewer before any translation work
    # happens — translating is the expensive bit, so we want to spend
    # those tokens only on the cards we'll actually return.
    if user is not None:
        canon = rank_cards_for_user(canon, user)
    canon = canon[:limit]
    if language == "en":
        return canon

    out: list[dict[str, Any]] = []
    for card in canon:
        # Defensive: if the canon doc is missing an ``id`` (e.g. a
        # legacy/partial document slipped into trend_reports) we
        # cannot key the translation cache by ``origin_id`` — skip
        # the translation step and surface the raw English card so
        # the feed never 500s on a single bad row.
        canon_id = card.get("id")
        if not canon_id:
            logger.warning(
                "fashion_scout_feed: canon card missing 'id' (bucket=%s date=%s)",
                card.get("bucket"),
                card.get("date"),
            )
            out.append(card)
            continue
        try:
            cached = await db.trend_reports.find_one(
                {
                    "origin_id": canon_id,
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
                # Persist for the next reader. ``insert_one`` failures
                # here (duplicate key from a concurrent writer, write
                # quorum hiccup, etc.) must NOT take down the whole
                # request — we still have a perfectly good translated
                # card to show; we just won't cache it this time.
                try:
                    await db.trend_reports.insert_one(
                        {**translated, "_origin": canon_id}
                    )
                except Exception as cache_exc:  # noqa: BLE001
                    logger.info(
                        "fashion_scout_feed: cache insert skipped (%s -> %s): %s",
                        canon_id,
                        language,
                        cache_exc,
                    )
                out.append({k: v for k, v in translated.items() if k != "_id"})
            else:
                out.append(card)
        except Exception as exc:  # noqa: BLE001
            # Last-resort: log and fall back to the English canon
            # card so a single broken translation never 500s the
            # whole feed for the user.
            logger.warning(
                "fashion_scout_feed: per-card failure (%s -> %s): %s",
                canon_id,
                language,
                exc,
            )
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
