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
    company_name: str | None = None
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

    # --- Phase 4P: PayPal payouts ---
    paypal_receiver_email: str | None = None

    # --- Phase TS-2 (Trend-Scout personalization) ---
    occupation: str | None = None


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    safe = {k: v for k, v in user.items() if k not in {"password_hash", "google_oauth"}}
    safe["google_connected"] = bool(user.get("google_oauth"))
    return safe


@router.patch("/me")
async def update_me(
    payload: UpdateUserIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Partial profile update.

    **Important — embedded-document merge semantics.** Mongo's
    ``$set`` on a nested dict (e.g. ``body_measurements``) wholesale
    replaces the dict, dropping every field not present in the
    incoming payload. That's the opposite of what users expect from
    a "PATCH" — and a real data-loss bug when a frontend form sends
    only the fields it knows about (e.g. a cropped/pruned body
    measurements blob from a partial form re-render).

    To make the endpoint safe under all callers, we **deep-merge**
    every dict-typed field into its existing value instead of
    overwriting it. Scalar fields keep ``$set`` semantics. Setting
    a dict field to ``{}`` explicitly is treated as "no change"
    (use a dedicated reset endpoint if you ever need to fully wipe
    a sub-document — none currently exists).
    """
    patch = payload.model_dump(exclude_none=True)
    if "style_profile" in patch and patch["style_profile"] is not None:
        patch["style_profile"] = patch["style_profile"] if isinstance(
            patch["style_profile"], dict
        ) else patch["style_profile"].model_dump()
    if "cultural_context" in patch and patch["cultural_context"] is not None:
        patch["cultural_context"] = patch["cultural_context"] if isinstance(
            patch["cultural_context"], dict
        ) else patch["cultural_context"].model_dump()

    # Embedded-document fields that must MERGE (not replace) so a
    # partial PATCH cannot wipe values the frontend wasn't aware of.
    _MERGEABLE_DICT_FIELDS = (
        "body_measurements",
        "address",
        "units",
        "hair",
        "home_location",
        "professional",
        "style_profile",
        "cultural_context",
    )

    db = get_db()
    set_ops: dict[str, Any] = {}
    for k, v in patch.items():
        if k in _MERGEABLE_DICT_FIELDS and isinstance(v, dict):
            # Mongo dot-notation: ``$set: {"body_measurements.chest": 92}``
            # leaves every other ``body_measurements.*`` field untouched.
            # Empty payload {} ⇒ no-op (correct: PATCH = "do nothing").
            for sub_k, sub_v in v.items():
                if sub_v is None:
                    continue
                # Allow "" as an explicit clear of a single sub-field —
                # the frontend pruning step already strips empties on
                # the way in, so reaching here means the caller
                # intentionally wants to blank that one cell.
                set_ops[f"{k}.{sub_k}"] = sub_v
        else:
            set_ops[k] = v
    set_ops["updated_at"] = datetime.now(timezone.utc).isoformat()
    if set_ops:
        await db.users.update_one({"id": user["id"]}, {"$set": set_ops})
    updated = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if updated is not None:
        updated.pop("password_hash", None)
        updated.pop("google_oauth", None)
    return updated or {}
