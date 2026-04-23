"""/api/v1/share — tiny, intentionally minimal read-only snapshot store.

For Phase S we only need to share a single outfit recommendation via a link.
Recipients can open the link without logging in; they see a read-only JSON
payload the frontend renders. Richer features (approval voting, comments,
receiver chat, expiring links) are deferred.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.db.database import get_db
from app.services.auth import get_current_user

router = APIRouter(prefix="/share", tags=["share"])


@router.post("/outfit", status_code=201)
async def share_outfit(
    payload: dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    outfit = payload.get("outfit")
    if not outfit or not isinstance(outfit, dict):
        raise HTTPException(400, "`outfit` (object) is required")
    snapshot = {
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "session_id": payload.get("session_id"),
        "outfit": outfit,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db = get_db()
    await db.shared_outfits.insert_one({**snapshot})
    # The frontend mints the fully-qualified URL so we don't have to know
    # the origin host server-side — keeps things portable across envs.
    return {
        "id": snapshot["id"],
        "owner_id": snapshot["owner_id"],
        "session_id": snapshot["session_id"],
        "created_at": snapshot["created_at"],
    }


@router.get("/outfit/{share_id}")
async def get_shared_outfit(share_id: str) -> dict[str, Any]:
    db = get_db()
    doc = await db.shared_outfits.find_one({"id": share_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Share not found")
    return doc
