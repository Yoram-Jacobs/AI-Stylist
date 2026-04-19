"""Google Calendar OAuth + events endpoints (Phase 4)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import settings
from app.services.auth import get_current_user
from app.services.calendar_service import calendar_service

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth/google", tags=["auth-google"])
calendar_router = APIRouter(prefix="/calendar", tags=["calendar"])

_STATE_EXPIRES_MIN = 15  # short-lived CSRF state


def _build_state(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "purpose": "google-oauth",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRES_MIN),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _read_state(token: str) -> str:
    try:
        data = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(400, "OAuth state token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(400, "Invalid OAuth state token") from exc
    if data.get("purpose") != "google-oauth" or not data.get("sub"):
        raise HTTPException(400, "Invalid OAuth state payload")
    return data["sub"]


# -------------------- auth routes --------------------
@auth_router.get("/start")
async def google_oauth_start(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate the Google authorization URL for the current DressApp user."""
    if not calendar_service.enabled:
        raise HTTPException(503, "Google OAuth not configured on server")
    state = _build_state(user["id"])
    url = calendar_service.build_authorization_url(state)
    return {"authorization_url": url, "state": state}


@auth_router.get("/callback")
async def google_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle Google's redirect. Persists tokens on the user and redirects
    the browser back to the frontend Profile page.
    """
    redirect_base = calendar_service.post_login_redirect or "/me"

    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(f"{redirect_base}?calendar=error&reason={error}")
    if not code or not state:
        return RedirectResponse(f"{redirect_base}?calendar=error&reason=missing_params")

    try:
        user_id = _read_state(state)
    except HTTPException as exc:
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason={exc.detail.replace(' ', '_')}"
        )

    try:
        tokens = await calendar_service.exchange_code(code)
    except Exception:  # noqa: BLE001
        logger.exception("Google token exchange failed")
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason=token_exchange_failed"
        )

    try:
        await calendar_service.persist_tokens_for_user(user_id, tokens)
    except Exception:  # noqa: BLE001
        logger.exception("Persisting Google tokens failed")
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason=persist_failed"
        )

    return RedirectResponse(f"{redirect_base}?calendar=connected")


@auth_router.post("/disconnect")
async def google_oauth_disconnect(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    await calendar_service.disconnect_user(user["id"])
    return {"status": "disconnected"}


# -------------------- calendar routes --------------------
@calendar_router.get("/status")
async def calendar_status(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    tokens = (user or {}).get("google_calendar_tokens") or {}
    return {
        "connected": bool(tokens.get("refresh_token")),
        "google_email": tokens.get("google_email"),
        "connected_at": tokens.get("connected_at"),
        "scope": tokens.get("scope"),
    }


@calendar_router.get("/upcoming")
async def calendar_upcoming(
    hours_ahead: int = Query(default=48, ge=1, le=168),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    events = await calendar_service.get_events_for_user(user, hours_ahead=hours_ahead)
    return {"events": events, "count": len(events)}
