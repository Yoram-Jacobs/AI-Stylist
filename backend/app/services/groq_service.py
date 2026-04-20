"""Groq Whisper-large-v3 transcription."""
from __future__ import annotations

import logging
from typing import Any

from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)


class GroqWhisperService:
    def __init__(self) -> None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not configured.")
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = settings.WHISPER_MODEL

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous Groq call (the SDK is thread-safe).

        Returns `{text, language, raw}`.
        """
        from app.services import provider_activity

        params: dict[str, Any] = {
            "file": (filename, audio_bytes, content_type),
            "model": self.model,
            "response_format": "verbose_json",
            "temperature": 0.0,
        }
        if language:
            params["language"] = language
        logger.info(
            "Groq Whisper transcribe model=%s bytes=%d", self.model, len(audio_bytes)
        )
        with provider_activity.Track("groq-whisper", {"bytes": len(audio_bytes)}):
            result = self.client.audio.transcriptions.create(**params)
        # groq SDK returns a pydantic-like object
        text = getattr(result, "text", None) or ""
        lang = getattr(result, "language", None)
        return {"text": text, "language": lang, "raw": _safe_dump(result)}


def _safe_dump(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return {"repr": repr(obj)}


groq_whisper_service = GroqWhisperService() if settings.GROQ_API_KEY else None
