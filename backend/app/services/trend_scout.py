"""Trend-Scout agent \u2014 autonomous daily fashion-trend synthesiser.

Responsibilities
----------------
* Run on a schedule (default: daily at 07:00 UTC).
* Call Gemini 2.5 Pro via the Emergent universal key to synthesise short,
  editorial cards for three evergreen DressApp buckets: runway, street,
  sustainability.
* Persist each run to the ``trend_reports`` collection with one document
  per bucket per day so the Home page can render a clean "daily edit".

Design notes
------------
* The generator is fully self-contained: it does not require an external
  news feed. Gemini produces the trend observation grounded in the user
  profile buckets. This is intentional \u2014 we can plug in a real signal
  source later without rewriting the rest of the system.
* The agent is idempotent for the day: if the most recent ``trend_reports``
  document for a bucket is from today, we skip regeneration.
* Errors never crash the scheduler \u2014 we log and move on.
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

BUCKETS: list[dict[str, str]] = [
    {
        "slug": "ss26-runway",
        "label": "SS26 Runway",
        "prompt": (
            "Summarise ONE concrete SS26 runway trend worth a closet update."
            " Focus on silhouettes, fabrics, or signature colours."
        ),
    },
    {
        "slug": "street",
        "label": "Street",
        "prompt": (
            "Name ONE street-style shift that's actually being worn (not "
            "editorial fantasy). Call out the key item + the styling move."
        ),
    },
    {
        "slug": "sustainability",
        "label": "Sustainability",
        "prompt": (
            "Pick ONE emerging sustainability story in fashion (resale, swap, "
            "materials, repair, rental) and state the user-facing implication."
        ),
    },
]

SYSTEM_PROMPT = (
    "You are DressApp's Trend-Scout \u2014 a sharp, concise fashion journalist."
    " Write for a reader who already dresses well and wants ONE actionable"
    " insight. Voice: editorial, confident, never salesy."
    "\n\nOutput contract: return ONLY a JSON object shaped like"
    ' {"headline": string (<= 7 words),'
    ' "body": string (1\u20132 sentences, <= 220 chars),'
    ' "tag": string (short all-caps category tag)}.'
    " No markdown, no prose outside JSON."
)


def _extract_json(raw: str) -> dict[str, Any]:
    """Resilient JSON extractor identical in spirit to the stylist brain."""
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


async def _generate_one(bucket: dict[str, str]) -> dict[str, Any] | None:
    """Generate one trend card. Returns None on failure \u2014 caller logs."""
    api_key = settings.EMERGENT_LLM_KEY
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY missing \u2014 cannot run Trend-Scout")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"trendscout-{bucket['slug']}-{uuid.uuid4().hex[:8]}",
        system_message=SYSTEM_PROMPT,
    )
    chat.with_model(
        settings.DEFAULT_STYLIST_PROVIDER, settings.DEFAULT_STYLIST_MODEL
    )
    try:
        raw = await chat.send_message(UserMessage(text=bucket["prompt"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trend-Scout LLM call failed for %s: %s", bucket["slug"], exc)
        return None
    parsed = _extract_json(raw or "")
    if not parsed.get("headline") or not parsed.get("body"):
        logger.warning(
            "Trend-Scout returned unparseable payload for %s: %s",
            bucket["slug"],
            (raw or "")[:200],
        )
        return None
    return {
        "headline": str(parsed["headline"])[:120],
        "body": str(parsed["body"])[:400],
        "tag": (parsed.get("tag") or bucket["label"]).upper()[:40],
    }


async def _already_today(bucket_slug: str) -> bool:
    db = get_db()
    today = date.today().isoformat()
    existing = await db.trend_reports.find_one({"bucket": bucket_slug, "date": today})
    return bool(existing)


async def run_trend_scout(*, force: bool = False) -> dict[str, Any]:
    """Generate and persist today's trend cards. Safe to call on demand."""
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
            "headline": card["headline"],
            "body": card["body"],
            "tag": card["tag"],
            "model": settings.DEFAULT_STYLIST_MODEL,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.trend_reports.replace_one(
            {"bucket": bucket["slug"], "date": today}, doc, upsert=True
        )
        results.append(doc)
    logger.info(
        "Trend-Scout run complete: generated=%d, skipped=%d",
        len(results),
        len(skipped),
    )
    return {
        "generated": [{k: v for k, v in r.items() if k != "_id"} for r in results],
        "skipped": skipped,
        "date": today,
    }


async def latest_trend_cards(limit_per_bucket: int = 1) -> list[dict[str, Any]]:
    """Return the most recent card for each bucket, newest first."""
    db = get_db()
    out: list[dict[str, Any]] = []
    for bucket in BUCKETS:
        cursor = (
            db.trend_reports.find({"bucket": bucket["slug"]}, {"_id": 0})
            .sort("date", -1)
            .limit(limit_per_bucket)
        )
        async for doc in cursor:
            out.append(doc)
    return out
