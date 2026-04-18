"""Google Calendar integration — structured stub for Phase 1.

Phase 1 exposes the shape of the calendar context consumed by the stylist
brain. The real OAuth flow + token refresh is implemented in Phase 4 once the
user provides Google OAuth client credentials.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings


class CalendarService:
    def __init__(self) -> None:
        self.enabled = bool(
            settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
        )

    async def get_events_for_user(
        self, user: dict[str, Any] | None, hours_ahead: int = 24
    ) -> list[dict[str, Any]]:
        if not self.enabled or not user or not user.get("google_oauth"):
            return []
        # TODO(Phase 4): real Google Calendar API call with token refresh.
        return []

    @staticmethod
    def infer_formality(event_title: str) -> str:
        title = (event_title or "").lower()
        if any(k in title for k in ["client", "pitch", "board", "interview", "gala", "wedding"]):
            return "formal"
        if any(k in title for k in ["standup", "1:1", "sync", "coffee", "lunch"]):
            return "casual"
        if any(k in title for k in ["demo", "presentation", "review"]):
            return "business"
        return "smart-casual"

    @staticmethod
    def mock_event(title: str, formality: str | None = None) -> dict[str, Any]:
        """Used by the POC to exercise the prompt builder without OAuth."""
        start = (datetime.now(timezone.utc) + timedelta(hours=16)).isoformat()
        return {
            "title": title,
            "start": start,
            "formality_hint": formality or CalendarService.infer_formality(title),
        }


calendar_service = CalendarService()
