"""Stylist orchestrator — combines every provider into `get_styling_advice`.

This is the “logic.py” called out in the Phase 1 requirements. It is
intentionally synchronous-looking from the outside so the `/api/v1/stylist`
route and the POC script both exercise the same code path.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from app.services.deepgram_service import deepgram_service
from app.services.gemini_image_service import gemini_image_service
from app.services.gemini_stylist import gemini_stylist_service, image_bytes_to_base64
from app.services.groq_service import groq_whisper_service
from app.services.hf_segmentation import hf_segmentation_service
from app.services.weather_service import weather_service

logger = logging.getLogger(__name__)


async def fetch_image_bytes(url_or_bytes: str | bytes) -> bytes:
    if isinstance(url_or_bytes, bytes):
        return url_or_bytes
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url_or_bytes, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


async def get_styling_advice(
    *,
    session_id: str,
    image_bytes: bytes | None,
    image_mime: str = "image/jpeg",
    user_text: str | None = None,
    voice_audio: bytes | None = None,
    voice_filename: str = "audio.webm",
    voice_mime: str = "audio/webm",
    do_infill: bool = False,
    infill_prompt: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    language: str = "en",
    voice_id: str = "aura-2-thalia-en",
    calendar_events: list[dict[str, Any]] | None = None,
    cultural_rules: list[dict[str, Any]] | None = None,
    user_profile: dict[str, Any] | None = None,
    closet_summary: list[dict[str, Any]] | None = None,
    synthesize_tts: bool = True,
) -> dict[str, Any]:
    """Run the full multimodal stylist pipeline and return a combined payload."""
    if not (user_text or voice_audio):
        raise ValueError("user_text or voice_audio is required")
    if gemini_stylist_service is None:
        raise RuntimeError("Gemini service not configured (EMERGENT_LLM_KEY missing)")

    latency: dict[str, int] = {}
    result: dict[str, Any] = {
        "transcript": user_text,
        "segmented_image_url": None,
        "infilled_image_url": None,
        "weather_summary": None,
        "calendar_summary": None,
        "outfit_recommendations": [],
        "reasoning_summary": "",
        "shopping_suggestions": [],
        "do_dont": [],
        "spoken_reply": "",
        "tts_audio_base64": None,
        "latency_ms": latency,
    }

    # --- 1. Transcribe if voice provided
    if voice_audio:
        if groq_whisper_service is None:
            raise RuntimeError("Groq service not configured (GROQ_API_KEY missing)")
        t0 = time.perf_counter()
        tx = groq_whisper_service.transcribe(
            voice_audio,
            filename=voice_filename,
            content_type=voice_mime,
            language=language if language != "auto" else None,
        )
        latency["whisper_ms"] = int((time.perf_counter() - t0) * 1000)
        result["transcript"] = tx["text"]

    final_user_text = (result["transcript"] or user_text or "").strip()
    if not final_user_text:
        raise ValueError("No user text available after transcription")

    # --- 2. Segment the garment if an image was supplied (Hugging Face SAM)
    if image_bytes and hf_segmentation_service is not None:
        t0 = time.perf_counter()
        try:
            seg = await hf_segmentation_service.segment_garment(image_bytes)
            if seg.get("image_b64"):
                result["segmented_image_url"] = (
                    f"data:{seg.get('mime_type', 'image/png')};base64,"
                    f"{seg['image_b64']}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Segmentation failed: %s", exc)
        latency["segmentation_ms"] = int((time.perf_counter() - t0) * 1000)

    # --- 3. Optional infill / edit (Gemini Nano Banana)
    if image_bytes and do_infill and infill_prompt and gemini_image_service is not None:
        t0 = time.perf_counter()
        try:
            edit = await gemini_image_service.edit(image_bytes, infill_prompt)
            if edit.get("image_b64"):
                result["infilled_image_url"] = (
                    f"data:{edit.get('mime_type', 'image/png')};base64,"
                    f"{edit['image_b64']}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Infill failed: %s", exc)
        latency["infill_ms"] = int((time.perf_counter() - t0) * 1000)

    # --- 4. Weather
    if lat is not None and lng is not None and weather_service is not None:
        t0 = time.perf_counter()
        try:
            weather = await weather_service.fetch(lat, lng)
            result["weather_summary"] = (
                f"{weather.get('temp_c')}°C {weather.get('condition')} in "
                f"{weather.get('city')}"
            )
            weather_ctx = weather
        except Exception as exc:  # noqa: BLE001
            logger.warning("Weather fetch failed: %s", exc)
            weather_ctx = None
        latency["weather_ms"] = int((time.perf_counter() - t0) * 1000)
    else:
        weather_ctx = None

    # --- 5. Calendar context summary
    if calendar_events:
        result["calendar_summary"] = ", ".join(
            f"{e.get('title')} [{e.get('formality_hint')}]" for e in calendar_events
        )

    # --- 6. Gemini 2.5 Pro styling brain
    image_b64 = image_bytes_to_base64(image_bytes) if image_bytes else None
    t0 = time.perf_counter()
    advice = await gemini_stylist_service.advise(
        session_id=session_id,
        user_text=final_user_text,
        image_base64=image_b64,
        image_mime=image_mime,
        weather=weather_ctx,
        calendar_events=calendar_events,
        cultural_rules=cultural_rules,
        user_profile=user_profile,
        closet_summary=closet_summary,
    )
    latency["gemini_ms"] = int((time.perf_counter() - t0) * 1000)

    result["outfit_recommendations"] = advice.get("outfit_recommendations", [])
    result["reasoning_summary"] = advice.get("reasoning_summary", "")
    result["shopping_suggestions"] = advice.get("shopping_suggestions", [])
    result["do_dont"] = advice.get("do_dont", [])
    result["spoken_reply"] = advice.get("spoken_reply") or advice.get(
        "reasoning_summary", ""
    )

    # --- 7. Deepgram Aura-2 TTS
    if synthesize_tts and result["spoken_reply"] and deepgram_service is not None:
        t0 = time.perf_counter()
        try:
            audio = await deepgram_service.speak_to_bytes(
                result["spoken_reply"], voice=voice_id, encoding="mp3"
            )
            result["tts_audio_base64"] = base64.b64encode(audio).decode("ascii")
        except Exception as exc:  # noqa: BLE001
            logger.warning("TTS synthesis failed: %s", exc)
        latency["tts_ms"] = int((time.perf_counter() - t0) * 1000)

    return result
