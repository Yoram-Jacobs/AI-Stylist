"""User profile routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.db.database import get_db
from app.models.schemas import CulturalContext, StyleProfile
from app.services.auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class UpdateUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    avatar_url: str | None = None
    locale: str | None = None
    preferred_language: str | None = None
    preferred_voice_id: str | None = None
    home_location: dict[str, Any] | None = None
    style_profile: StyleProfile | None = None
    cultural_context: CulturalContext | None = None

    # --- Extended profile (Phase T) ---
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    personal_status: str | None = None
    address: dict[str, Any] | None = None
    units: dict[str, Any] | None = None
    face_photo_url: str | None = None
    body_photo_url: str | None = None
    body_measurements: dict[str, Any] | None = None
    hair: dict[str, Any] | None = None

    # --- Phase U: Professional ---
    professional: dict[str, Any] | None = None


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    safe = {k: v for k, v in user.items() if k not in {"password_hash", "google_oauth"}}
    safe["google_connected"] = bool(user.get("google_oauth"))
    return safe


@router.patch("/me")
async def update_me(
    payload: UpdateUserIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    patch = payload.model_dump(exclude_none=True)
    if "style_profile" in patch and patch["style_profile"] is not None:
        patch["style_profile"] = patch["style_profile"] if isinstance(
            patch["style_profile"], dict
        ) else patch["style_profile"].model_dump()
    if "cultural_context" in patch and patch["cultural_context"] is not None:
        patch["cultural_context"] = patch["cultural_context"] if isinstance(
            patch["cultural_context"], dict
        ) else patch["cultural_context"].model_dump()
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_db()
    await db.users.update_one({"id": user["id"]}, {"$set": patch})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if updated is not None:
        updated.pop("password_hash", None)
        updated.pop("google_oauth", None)
    return updated or {}
