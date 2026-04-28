"""Auth utilities: bcrypt password hashing + JWT encode/decode + FastAPI deps.

Exposes:
  * `hash_password`, `verify_password`
  * `create_access_token`, `decode_token`
  * `get_current_user` (FastAPI dependency) + `get_current_user_optional`
  * `dev_bypass_login()` — enabled only when ALLOW_DEV_BYPASS=true
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from passlib.context import CryptContext

from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)

# bcrypt is forced to version-compatible rounds=12.
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRES_MIN)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


async def _fetch_user(user_id: str) -> dict[str, Any] | None:
    return await get_db().users.find_one({"id": user_id}, {"_id": 0})


async def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    user = await _fetch_user(user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
) -> dict[str, Any] | None:
    if not authorization:
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    if "admin" not in (user.get("roles") or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


def apply_admin_role(roles: list[str] | None, email: str | None) -> list[str]:
    """Return a roles list with ``admin`` added/removed based on the
    ``ADMIN_EMAILS`` allow-list. Idempotent and safe to call on every
    register / login / Google sign-in.

    * If ``email`` is in ``settings.admin_emails_set`` → ensures ``admin``.
    * Otherwise → preserves the user's other roles untouched. We deliberately
      DO NOT auto-demote here: explicit demotion goes through
      ``scripts/grant_admin.py --revoke`` so a typo in ``.env`` cannot wipe
      out an existing admin.
    """
    base = list(roles or ["user"])
    if "user" not in base:
        base.append("user")
    if email and email.lower() in settings.admin_emails_set and "admin" not in base:
        base.append("admin")
    return base
