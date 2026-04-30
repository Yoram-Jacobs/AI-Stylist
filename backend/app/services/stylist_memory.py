"""Stylist memory helpers — Durable-Object equivalent built on Mongo.

This module now supports *multiple concurrent conversations* per user (the
ChatGPT-style thread list). The previous single-session behavior is preserved
through ``get_or_create_active_session`` which backs the default stylist
endpoint when no explicit ``session_id`` is supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.database import get_db
from app.models.schemas import StylistMessage, StylistSession
from app.services import repos


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------
async def get_or_create_active_session(user_id: str) -> dict[str, Any]:
    """Return the user's most recently active (non-archived) session,
    creating a fresh one if none exists."""
    db = get_db()
    sess = await repos.find_one(
        db.stylist_sessions,
        {"user_id": user_id, "archived": {"$ne": True}},
        sort=[("last_active_at", -1)],
    )
    if sess:
        return sess
    return await create_session(user_id)


async def create_session(user_id: str, title: str | None = None) -> dict[str, Any]:
    """Create a new conversation session for the user."""
    new = StylistSession(user_id=user_id, title=title).model_dump()
    db = get_db()
    await repos.insert(db.stylist_sessions, new)
    return new


async def list_sessions(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first list of the user's sessions for the conversation sidebar."""
    db = get_db()
    rows = await repos.find_many(
        db.stylist_sessions,
        {"user_id": user_id, "archived": {"$ne": True}},
        sort=[("last_active_at", -1)],
        limit=limit,
    )
    return rows


async def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    """Fetch a session by id with ownership enforcement."""
    db = get_db()
    return await repos.find_one(
        db.stylist_sessions, {"id": session_id, "user_id": user_id}
    )


async def update_session(
    session_id: str,
    user_id: str,
    *,
    title: str | None = None,
    snippet: str | None = None,
) -> dict[str, Any] | None:
    db = get_db()
    patch: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if title is not None:
        patch["title"] = title
    if snippet is not None:
        patch["snippet"] = snippet
    await db.stylist_sessions.update_one(
        {"id": session_id, "user_id": user_id}, {"$set": patch}
    )
    return await get_session(session_id, user_id)


async def delete_session(session_id: str, user_id: str) -> bool:
    """Remove a session (and cascade its messages) — returns True if deleted."""
    db = get_db()
    res = await db.stylist_sessions.delete_one(
        {"id": session_id, "user_id": user_id}
    )
    if res.deleted_count:
        await db.stylist_messages.delete_many({"session_id": session_id})
        return True
    return False


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
async def recent_messages(session_id: str, limit: int = 6) -> list[dict[str, Any]]:
    """Return oldest-first list of recent messages for Gemini context."""
    db = get_db()
    rows = await repos.find_many(
        db.stylist_messages,
        {"session_id": session_id},
        sort=[("created_at", -1)],
        limit=limit,
    )
    return list(reversed(rows))


async def full_history(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return oldest-first list of messages for rendering in the chat panel."""
    db = get_db()
    rows = await repos.find_many(
        db.stylist_messages,
        {"session_id": session_id},
        sort=[("created_at", 1)],
        limit=limit,
    )
    return rows


async def append_message(
    session_id: str,
    role: str,
    input_modality: str,
    *,
    transcript: str | None = None,
    image_refs: list[str] | None = None,
    context: dict[str, Any] | None = None,
    assistant_payload: dict[str, Any] | None = None,
    tts_audio_ref: str | None = None,
    latency_ms: dict[str, int] | None = None,
) -> dict[str, Any]:
    db = get_db()
    msg = StylistMessage(
        session_id=session_id,
        role=role,  # type: ignore[arg-type]
        input_modality=input_modality,  # type: ignore[arg-type]
        transcript=transcript,
        image_refs=image_refs or [],
        context=context or {},
        assistant_payload=assistant_payload,
        tts_audio_ref=tts_audio_ref,
        latency_ms=latency_ms or {},
    )
    doc = msg.model_dump()
    await repos.insert(db.stylist_messages, doc)
    # bump session counters + snippet (only for user turns so the sidebar
    # preview is meaningful).
    session_patch: dict[str, Any] = {
        "last_active_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if role == "user" and transcript:
        # Truncate to a manageable preview length for the sidebar.
        session_patch["snippet"] = transcript.strip()[:140]
    await db.stylist_sessions.update_one(
        {"id": session_id},
        {"$inc": {"turns": 1}, "$set": session_patch},
    )
    return doc


# ---------------------------------------------------------------------------
# Closet summary (used by the stylist for grounding)
# ---------------------------------------------------------------------------
async def closet_summary_for(user_id: str, limit: int = 40) -> list[dict[str, Any]]:
    db = get_db()
    rows = await repos.find_many(
        db.closet_items,
        {
            "user_id": user_id,
            # Phase Z2 \u2014 user-approved duplicates are excluded from
            # the grounding context the Stylist Brain receives, so it
            # cannot reason about an item it shouldn't surface.
            "is_duplicate": {"$ne": True},
        },
        sort=[("updated_at", -1)],
        limit=limit,
    )
    return [
        {
            "id": r["id"],
            "title": r.get("title"),
            "category": r.get("category"),
            "sub_category": r.get("sub_category"),
            "color": r.get("color"),
            "material": r.get("material"),
            "pattern": r.get("pattern"),
            "formality": r.get("formality"),
            "season": r.get("season") or [],
            "tags": r.get("tags") or [],
            "source": r.get("source"),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
get_or_create_session = get_or_create_active_session  # legacy imports
