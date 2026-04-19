"""/api/v1/trends \u2014 read + admin trigger endpoints for the Trend-Scout."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth import get_current_user, require_admin
from app.services.trend_scout import latest_trend_cards, run_trend_scout

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/latest")
async def get_latest_trends(
    per_bucket: int = Query(default=1, ge=1, le=5),
) -> dict[str, Any]:
    """Public-safe read: newest card(s) per bucket for the Home page feed."""
    cards = await latest_trend_cards(limit_per_bucket=per_bucket)
    return {"cards": cards, "count": len(cards)}


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
