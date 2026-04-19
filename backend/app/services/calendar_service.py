"""Google Calendar integration — real OAuth 2.0 + Events API (Phase 4).

Flow summary
------------
1. ``GET  /api/v1/auth/google/start`` — logged-in user requests to connect
   Calendar. We generate a signed JWT state token carrying the DressApp
   ``user_id`` and return the Google authorization URL.
2. ``GET  /api/v1/auth/google/callback`` — Google redirects back with
   ``code`` and our ``state``. We verify state, exchange the code for
   tokens, and persist ``google_calendar_tokens`` on the user document.
3. ``POST /api/v1/auth/google/disconnect`` — clears tokens.
4. ``GET  /api/v1/calendar/upcoming`` — lists upcoming events; refreshes
   the access token transparently when expired.

Stylist integration: ``calendar_service.get_events_for_user`` is used by
``/api/v1/stylist`` so real events replace the previous mock when a user
is connected.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class CalendarService:
    """Thin facade over Google's OAuth + Calendar v3 API."""

    def __init__(self) -> None:
        self.client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        self.client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
        self.post_login_redirect = (
            settings.GOOGLE_OAUTH_POST_LOGIN_REDIRECT or "/me"
        )

    @property
    def enabled(self) -> bool:
        return bool(
            self.client_id and self.client_secret and self.redirect_uri
        )

    # -------------------- OAuth URL --------------------
    def build_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        from urllib.parse import urlencode

        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    # -------------------- token exchange --------------------
    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Swap an auth code for access+refresh tokens. Raises on failure."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Google token exchange failed ({resp.status_code}): {resp.text[:200]}"
            )
        return resp.json()

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        resp.raise_for_status()
        return resp.json()

    # -------------------- persistence helpers --------------------
    @staticmethod
    def _tokens_to_doc(tokens: dict[str, Any], email: str | None) -> dict[str, Any]:
        expires_at = None
        if tokens.get("expires_in"):
            expires_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=int(tokens["expires_in"]) - 30)
            ).isoformat()
        return {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope"),
            "expires_at": expires_at,
            "google_email": email,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def persist_tokens_for_user(
        self, user_id: str, tokens: dict[str, Any]
    ) -> dict[str, Any]:
        userinfo: dict[str, Any] = {}
        if tokens.get("access_token"):
            try:
                userinfo = await self.fetch_userinfo(tokens["access_token"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to fetch Google userinfo: %s", exc)
        doc = self._tokens_to_doc(tokens, userinfo.get("email"))
        db = get_db()
        # Preserve the previously stored refresh_token if Google didn't send a
        # new one (Google only returns refresh_token on first consent).
        existing = await db.users.find_one({"id": user_id}) or {}
        prev = (existing.get("google_calendar_tokens") or {}) if existing else {}
        if not doc.get("refresh_token") and prev.get("refresh_token"):
            doc["refresh_token"] = prev["refresh_token"]
        await db.users.update_one(
            {"id": user_id}, {"$set": {"google_calendar_tokens": doc}}
        )
        return doc

    async def disconnect_user(self, user_id: str) -> None:
        db = get_db()
        user = await db.users.find_one({"id": user_id}) or {}
        tokens = user.get("google_calendar_tokens") or {}
        token = tokens.get("refresh_token") or tokens.get("access_token")
        if token:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        GOOGLE_REVOKE_URL,
                        data={"token": token},
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Google token revoke call failed: %s", exc)
        await db.users.update_one(
            {"id": user_id}, {"$unset": {"google_calendar_tokens": ""}}
        )

    # -------------------- events --------------------
    async def get_events_for_user(
        self, user: dict[str, Any] | None, hours_ahead: int = 48
    ) -> list[dict[str, Any]]:
        """Return a compact list of upcoming events for the stylist context.

        Each event is simplified to ``{title, start, formality_hint}`` so the
        LLM prompt stays compact.
        """
        if not self.enabled or not user:
            return []
        tokens = user.get("google_calendar_tokens")
        if not tokens or not tokens.get("refresh_token"):
            return []

        try:
            service = await self._build_service(user["id"], tokens)
            now = datetime.now(timezone.utc)
            horizon = now + timedelta(hours=hours_ahead)
            events_resp = service.events().list(
                calendarId="primary",
                timeMin=now.isoformat().replace("+00:00", "Z"),
                timeMax=horizon.isoformat().replace("+00:00", "Z"),
                singleEvents=True,
                orderBy="startTime",
                maxResults=10,
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Calendar events fetch failed: %s", exc)
            return []

        simplified: list[dict[str, Any]] = []
        for ev in events_resp.get("items", []) or []:
            title = ev.get("summary") or "(untitled)"
            start = (
                (ev.get("start") or {}).get("dateTime")
                or (ev.get("start") or {}).get("date")
            )
            simplified.append(
                {
                    "title": title,
                    "start": start,
                    "formality_hint": self.infer_formality(title),
                    "location": ev.get("location"),
                }
            )
        return simplified

    async def _build_service(
        self, user_id: str, tokens: dict[str, Any]
    ) -> Any:
        """Build an authenticated googleapiclient service; refresh if needed."""
        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=GOOGLE_TOKEN_URL,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=SCOPES,
        )
        if not creds.valid and creds.refresh_token:
            # The library does a sync HTTP call; this is acceptable here.
            creds.refresh(GoogleAuthRequest())
            # Persist refreshed token for subsequent calls.
            db = get_db()
            await db.users.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "google_calendar_tokens.access_token": creds.token,
                        "google_calendar_tokens.expires_at": (
                            datetime.now(timezone.utc) + timedelta(minutes=50)
                        ).isoformat(),
                    }
                },
            )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    # -------------------- helpers --------------------
    @staticmethod
    def infer_formality(event_title: str) -> str:
        title = (event_title or "").lower()
        if any(k in title for k in ["client", "pitch", "board", "interview", "gala", "wedding"]):
            return "formal"
        if any(k in title for k in ["standup", "1:1", "sync", "coffee", "lunch"]):
            return "casual"
        if any(k in title for k in ["demo", "presentation", "review", "meeting"]):
            return "business"
        return "smart-casual"

    @staticmethod
    def mock_event(title: str, formality: str | None = None) -> dict[str, Any]:
        """Used by the POC/stylist when no real events are available."""
        start = (datetime.now(timezone.utc) + timedelta(hours=16)).isoformat()
        return {
            "title": title,
            "start": start,
            "formality_hint": formality or CalendarService.infer_formality(title),
        }


calendar_service = CalendarService()
