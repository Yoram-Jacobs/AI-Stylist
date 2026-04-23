"""/api/v1/stylist — authenticated multimodal stylist route (Phase 2 + R).

Phase R adds multi-session support:
  * accepts an optional ``session_id`` form field on POST /stylist
  * sessions CRUD under /stylist/sessions
  * history is per-session
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.services.auth import get_current_user
from app.services.calendar_service import calendar_service
from app.services.logic import get_styling_advice
from app.services.session_titles import generate_session_title
from app.services.stylist_memory import (
    append_message,
    closet_summary_for,
    create_session,
    delete_session,
    full_history,
    get_or_create_active_session,
    get_session,
    list_sessions,
    recent_messages,
    update_session,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stylist", tags=["stylist"])


def _safe_session(session: dict) -> dict:
    """Strip Mongo _id to keep the payload JSON-safe."""
    return {k: v for k, v in session.items() if k != "_id"}


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------
@router.get("/sessions")
async def stylist_sessions(
    user: dict = Depends(get_current_user),
    limit: int = 50,
) -> dict[str, Any]:
    """Newest-first list of the user's conversation sessions."""
    sessions = await list_sessions(user["id"], limit=limit)
    return {"sessions": [_safe_session(s) for s in sessions]}


@router.post("/sessions")
async def stylist_create_session(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a fresh session. The title will be filled on the first turn."""
    session = await create_session(user["id"])
    return _safe_session(session)


@router.delete("/sessions/{session_id}")
async def stylist_delete_session(
    session_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    ok = await delete_session(session_id, user["id"])
    if not ok:
        raise HTTPException(404, "Session not found")
    return {"deleted": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# POST /stylist — primary conversational endpoint
# ---------------------------------------------------------------------------
@router.post("")
async def stylist_endpoint(
    text: str | None = Form(default=None),
    voice_audio: UploadFile | None = File(default=None),
    image: UploadFile | None = File(default=None),
    do_infill: bool = Form(default=False),
    infill_prompt: str | None = Form(default=None),
    lat: float | None = Form(default=None),
    lng: float | None = Form(default=None),
    include_calendar: bool = Form(default=False),
    language: str = Form(default="en"),
    voice_id: str = Form(default="aura-2-thalia-en"),
    occasion: str | None = Form(default=None),
    skip_tts: bool = Form(default=False),
    session_id: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    if not text and not voice_audio:
        raise HTTPException(400, "Provide `text` or `voice_audio`.")

    image_bytes: bytes | None = None
    image_mime = "image/jpeg"
    if image is not None:
        image_bytes = await image.read()
        image_mime = image.content_type or "image/jpeg"

    audio_bytes: bytes | None = None
    audio_filename = "audio.webm"
    audio_mime = "audio/webm"
    if voice_audio is not None:
        audio_bytes = await voice_audio.read()
        audio_filename = voice_audio.filename or audio_filename
        audio_mime = voice_audio.content_type or audio_mime

    calendar_events: list[dict[str, Any]] | None = None
    if include_calendar:
        real_events = await calendar_service.get_events_for_user(user)
        if real_events:
            calendar_events = real_events
        else:
            calendar_events = [calendar_service.mock_event(occasion or "Work day")]

    if lat is None or lng is None:
        home = user.get("home_location") or {}
        lat = lat if lat is not None else home.get("lat")
        lng = lng if lng is not None else home.get("lng")

    # Resolve target session: explicit id > last active > create fresh.
    session: dict | None = None
    if session_id:
        session = await get_session(session_id, user["id"])
        if not session:
            raise HTTPException(404, "Session not found")
    else:
        session = await get_or_create_active_session(user["id"])

    is_first_turn = (session.get("turns") or 0) == 0

    history = await recent_messages(session["id"], limit=4)
    closet = await closet_summary_for(user["id"], limit=40)

    user_profile = {
        "preferred_language": (language or user.get("preferred_language") or "en").lower(),
        "preferred_voice_id": user.get("preferred_voice_id", voice_id),
        "style_profile": user.get("style_profile"),
        "cultural_context": user.get("cultural_context"),
        "conversation_history": [
            {
                "role": m.get("role"),
                "transcript": m.get("transcript"),
                "payload": m.get("assistant_payload"),
            }
            for m in history
        ],
    }

    await append_message(
        session_id=session["id"],
        role="user",
        input_modality=(
            "image+voice"
            if image_bytes and audio_bytes
            else "image+text"
            if image_bytes
            else "voice"
            if audio_bytes
            else "text"
        ),
        transcript=text,
        image_refs=[],
        context={"lat": lat, "lng": lng, "include_calendar": include_calendar},
    )

    # Kick off title generation for brand-new sessions. We do it synchronously
    # because it's a fast Gemini Flash call and we want the sidebar label
    # populated by the time the response arrives. Failures are non-fatal.
    if is_first_turn and text:
        try:
            title = await generate_session_title(text, language=language)
            if title:
                await update_session(session["id"], user["id"], title=title)
                session["title"] = title
        except Exception as exc:  # noqa: BLE001
            logger.warning("Title generation failed for %s: %s", session["id"], exc)

    try:
        advice = await get_styling_advice(
            session_id=session["id"],
            image_bytes=image_bytes,
            image_mime=image_mime,
            user_text=text,
            voice_audio=audio_bytes,
            voice_filename=audio_filename,
            voice_mime=audio_mime,
            do_infill=do_infill,
            infill_prompt=infill_prompt,
            lat=lat,
            lng=lng,
            language=language,
            voice_id=voice_id,
            calendar_events=calendar_events,
            cultural_rules=None,
            user_profile=user_profile,
            closet_summary=closet,
            synthesize_tts=not skip_tts,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Stylist misconfiguration")
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stylist pipeline failed")
        raise HTTPException(500, f"Stylist pipeline error: {exc}") from exc

    await append_message(
        session_id=session["id"],
        role="assistant",
        input_modality="text",
        transcript=advice.get("reasoning_summary") or "",
        assistant_payload={
            k: advice.get(k)
            for k in (
                "outfit_recommendations",
                "shopping_suggestions",
                "do_dont",
                "weather_summary",
                "calendar_summary",
                "segmented_image_url",
                "infilled_image_url",
                "spoken_reply",
            )
        },
        latency_ms=advice.get("latency_ms") or {},
    )

    return {
        "session_id": session["id"],
        "session": _safe_session(
            await get_session(session["id"], user["id"]) or session
        ),
        "advice": advice,
    }


# ---------------------------------------------------------------------------
# GET /stylist/history
# ---------------------------------------------------------------------------
@router.get("/history")
async def stylist_history(
    session_id: str | None = None,
    limit: int = 200,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return full message history for a specific session (defaults to the
    user's most recent active session)."""
    if session_id:
        session = await get_session(session_id, user["id"])
        if not session:
            raise HTTPException(404, "Session not found")
    else:
        session = await get_or_create_active_session(user["id"])
    msgs = await full_history(session["id"], limit=limit)
    return {
        "session_id": session["id"],
        "session": _safe_session(session),
        "messages": [{k: v for k, v in m.items() if k != "_id"} for m in msgs],
    }
