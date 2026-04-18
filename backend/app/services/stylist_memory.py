"""Stylist memory helpers — Durable-Object equivalent built on Mongo."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.database import get_db
from app.models.schemas import StylistMessage, StylistSession
from app.services import repos


async def get_or_create_session(user_id: str) -> dict[str, Any]:
    db = get_db()
    sess = await repos.find_one(db.stylist_sessions, {"user_id": user_id})
    if sess:
        return sess
    new = StylistSession(user_id=user_id).model_dump()
    await repos.insert(db.stylist_sessions, new)
    return new


async def recent_messages(session_id: str, limit: int = 6) -> list[dict[str, Any]]:
    db = get_db()
    rows = await repos.find_many(
        db.stylist_messages,
        {"session_id": session_id},
        sort=[("created_at", -1)],
        limit=limit,
    )
    return list(reversed(rows))  # oldest-first for the LLM context


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
    # bump session counters
    await db.stylist_sessions.update_one(
        {"id": _session_id_for(session_id)} if False else {"id": session_id},
        {
            "$inc": {"turns": 1},
            "$set": {
                "last_active_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    )
    return doc


def _session_id_for(sid: str) -> str:
    return sid  # placeholder to keep structure readable


async def closet_summary_for(user_id: str, limit: int = 40) -> list[dict[str, Any]]:
    db = get_db()
    rows = await repos.find_many(
        db.closet_items,
        {"user_id": user_id},
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
