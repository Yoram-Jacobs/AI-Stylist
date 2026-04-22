"""/api/v1/stylist — authenticated multimodal stylist route (Phase 2).

Changes vs Phase 1:
  * Requires a user (JWT bearer or dev-bypass).
  * Hydrates `closet_summary` from the user's actual closet.
  * Persists the user + assistant turns into `stylist_sessions` + `stylist_messages`.
  * Hydrates the last few conversation turns as context for Gemini.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.services.auth import get_current_user
from app.services.calendar_service import calendar_service
from app.services.logic import get_styling_advice
from app.services.stylist_memory import (
    append_message,
    closet_summary_for,
    get_or_create_session,
    recent_messages,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stylist", tags=["stylist"])


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
            # Fall back to a single mocked event so the stylist still has
            # something to ground its reasoning when the user is not
            # connected to Google Calendar.
            calendar_events = [calendar_service.mock_event(occasion or "Work day")]

    # Determine / prefer the user's home location if lat/lng not supplied.
    if lat is None or lng is None:
        home = user.get("home_location") or {}
        lat = lat if lat is not None else home.get("lat")
        lng = lng if lng is not None else home.get("lng")

    session = await get_or_create_session(user["id"])
    history = await recent_messages(session["id"], limit=4)
    closet = await closet_summary_for(user["id"], limit=40)

    user_profile = {
        "preferred_language": user.get("preferred_language", "en"),
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

    # Persist the user turn BEFORE calling providers so we never lose intent.
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

    return {"session_id": session["id"], "advice": advice}


@router.get("/history")
async def stylist_history(
    limit: int = 20,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    session = await get_or_create_session(user["id"])
    msgs = await recent_messages(session["id"], limit=limit)
    return {"session_id": session["id"], "messages": msgs}
