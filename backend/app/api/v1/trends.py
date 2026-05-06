"""/api/v1/trends \u2014 read + admin trigger endpoints for the Trend-Scout."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import get_db
from app.services.auth import get_current_user, require_admin
from app.services.trend_scout import (
    BUCKETS,
    fashion_scout_feed,
    latest_trend_cards,
    run_trend_scout,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/latest")
async def get_latest_trends(
    per_bucket: int = Query(default=1, ge=1, le=5),
) -> dict[str, Any]:
    """Public-safe read: newest card(s) per bucket for the Home page feed."""
    cards = await latest_trend_cards(limit_per_bucket=per_bucket)
    return {"cards": cards, "count": len(cards)}


@router.get("/last_refresh")
async def get_last_refresh() -> dict[str, Any]:
    """Diagnostics endpoint — when did each bucket last refresh?

    Returns the newest ``created_at`` across all English Trend-Scout
    cards plus a per-bucket map. Public-safe (the data here is the
    same surface as ``/trends/latest``); used by the home-page admin
    refresh button to show staleness *and* by support for triage.
    """
    db = get_db()
    out_buckets: dict[str, str | None] = {}
    newest_iso: str | None = None
    for bucket in BUCKETS:
        latest = await db.trend_reports.find_one(
            {"bucket": bucket["slug"], "language": {"$in": [None, "en"]}},
            sort=[("created_at", -1)],
            projection={"_id": 0, "created_at": 1, "date": 1},
        )
        ts = (latest or {}).get("created_at")
        out_buckets[bucket["slug"]] = ts
        if ts and (newest_iso is None or ts > newest_iso):
            newest_iso = ts
    # Compute a friendly "stale_for_seconds" so the UI doesn't have to
    # parse ISO strings.
    stale_for_seconds: int | None = None
    if newest_iso:
        try:
            newest = datetime.fromisoformat(newest_iso.replace("Z", "+00:00"))
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=timezone.utc)
            stale_for_seconds = int(
                (datetime.now(timezone.utc) - newest).total_seconds()
            )
        except (TypeError, ValueError):
            stale_for_seconds = None
    return {
        "newest_created_at": newest_iso,
        "stale_for_seconds": stale_for_seconds,
        "buckets": out_buckets,
    }


@router.get("/fashion-scout")
async def get_fashion_scout_feed(
    limit: int = Query(default=12, ge=1, le=50),
    language: str | None = Query(default=None, max_length=8),
    country: str | None = Query(default=None, max_length=4),
) -> dict[str, Any]:
    """Newest-first flat feed for the Stylist right-panel news-flash.

    Wrapped in a top-level guard so a transient DB / translator error
    never returns a 500 to the user — we degrade to an empty feed
    instead and log the underlying cause for support triage.
    """
    try:
        cards = await fashion_scout_feed(
            limit=limit, language=language, country=country
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "fashion_scout endpoint failed (limit=%s language=%s country=%s): %s",
            limit,
            language,
            country,
            exc,
        )
        cards = []
    return {"cards": cards, "count": len(cards), "language": language or "en"}


@router.post("/run-now")
async def run_trend_scout_now(
    force: bool = Query(default=False),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only trigger for an immediate Trend-Scout run (for testing)."""
    return await run_trend_scout(force=force)


@router.post("/run-now-dev")
async def run_trend_scout_now_dev(
    force: bool = Query(default=True),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Dev helper: any authenticated user can trigger a run while we don't
    yet have a dedicated admin UI. Disabled in production by simply not
    exposing this route to non-dev deployments (toggle via config if needed).
    """
    if not user:
        raise HTTPException(401, "auth required")
    return await run_trend_scout(force=force)
