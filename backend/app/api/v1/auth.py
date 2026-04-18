"""Auth routes: register, login, /me, dev-bypass."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.db.database import get_db
from app.models.schemas import User
from app.services import repos
from app.services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None
    preferred_language: str = "en"
    preferred_voice_id: str = "aura-2-thalia-en"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in user.items() if k not in {"password_hash", "google_oauth"}}
    out["google_connected"] = bool(user.get("google_oauth"))
    return out


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(payload: RegisterIn) -> TokenOut:
    db = get_db()
    existing = await db.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        display_name=payload.display_name or payload.email.split("@")[0],
        preferred_language=payload.preferred_language,
        preferred_voice_id=payload.preferred_voice_id,
    )
    doc = user.model_dump()
    await repos.insert(db.users, doc)
    logger.info("user registered email=%s id=%s", user.email, user.id)
    token = create_access_token(user.id, {"email": user.email})
    return TokenOut(access_token=token, user=_public_user(doc))


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn) -> TokenOut:
    db = get_db()
    user = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(user["id"], {"email": user["email"]})
    return TokenOut(access_token=token, user=_public_user(user))


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return _public_user(user)


@router.post("/dev-bypass", response_model=TokenOut)
async def dev_bypass() -> TokenOut:
    """Creates / logs in as a fixed test user.

    REMOVE BEFORE PRODUCTION. Controlled by `ALLOW_DEV_BYPASS=true`.
    """
    if not settings.ALLOW_DEV_BYPASS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dev bypass disabled")

    db = get_db()
    email = "dev@dressapp.io"
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        new_user = User(
            email=email,
            password_hash=hash_password("DevPass123!"),
            display_name="Dev User",
            roles=["user", "admin"],
            preferred_language="en",
            preferred_voice_id="aura-2-thalia-en",
            home_location={"lat": 40.758, "lng": -73.9855, "city": "New York"},
        )
        doc = new_user.model_dump()
        await repos.insert(db.users, doc)
        user = doc
    else:
        await db.users.update_one(
            {"email": email},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    token = create_access_token(user["id"], {"email": user["email"], "dev": True})
    return TokenOut(access_token=token, user=_public_user(user))
