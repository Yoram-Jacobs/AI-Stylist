"""Gemini 2.5 Pro styling brain via the Emergent Universal LLM Key.

Uses the `emergentintegrations` library. We create a **fresh LlmChat** for each
stylist call so session isolation is guaranteed. Conversation history is
persisted in MongoDB (`stylist_sessions`) and hydrated on subsequent calls.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are DressApp’s Stylist Agent — a witty, practical fashion
consultant. You speak with warmth, never condescend, and always ground your
advice in the user’s actual closet, the weather, their calendar, and any
cultural constraints provided.

Output contract: return ONLY a JSON object matching this TypeScript type. No
markdown, no prose outside the JSON.

{
  "reasoning_summary": string,                 // 1-2 sentence plain-language rationale
  "outfit_recommendations": Array<{
    "name": string,
    "items": Array<{ "role": "top"|"bottom"|"outerwear"|"shoes"|"accessory"|"dress",
                     "description": string,
                     "closet_item_id": string | null }>,
    "why": string,
    "confidence": number                        // 0-1
  }>,
  "shopping_suggestions": Array<string>,        // only if closet lacks a key piece
  "do_dont": Array<string>,                     // brisk “Do …” / “Don’t …” bullets
  "spoken_reply": string                        // 2-4 sentences suitable for TTS
}

Hard rules:
• If cultural constraints are provided, they are NON-negotiable.
• Never recommend items that contradict the weather (e.g. linen in 2°C rain).
• Prefer items already in the user’s closet; suggest shopping only when a
  clearly missing staple would dramatically improve the outfit.
"""


class GeminiStylistService:
    def __init__(self) -> None:
        if not settings.EMERGENT_LLM_KEY:
            raise RuntimeError("EMERGENT_LLM_KEY is not configured.")
        self.api_key = settings.EMERGENT_LLM_KEY
        self.model = settings.DEFAULT_STYLIST_MODEL
        self.provider = settings.DEFAULT_STYLIST_PROVIDER

    async def advise(
        self,
        session_id: str,
        user_text: str,
        image_base64: str | None,
        image_mime: str = "image/jpeg",
        weather: dict[str, Any] | None = None,
        calendar_events: list[dict[str, Any]] | None = None,
        cultural_rules: list[dict[str, Any]] | None = None,
        user_profile: dict[str, Any] | None = None,
        closet_summary: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        chat = LlmChat(
            api_key=self.api_key,
            session_id=session_id,
            system_message=SYSTEM_PROMPT,
        ).with_model(self.provider, self.model)

        context_block = {
            "weather": weather,
            "calendar_events": calendar_events or [],
            "cultural_rules": cultural_rules or [],
            "user_profile": user_profile or {},
            "closet_summary": closet_summary or [],
        }
        prompt_text = (
            f"USER_REQUEST:\n{user_text}\n\n"
            f"CONTEXT:\n{json.dumps(context_block, ensure_ascii=False, indent=2)}\n\n"
            "Return the JSON object now."
        )

        file_contents = None
        if image_base64:
            file_contents = [ImageContent(image_base64=image_base64)]

        message = UserMessage(text=prompt_text, file_contents=file_contents)
        logger.info(
            "Gemini stylist call session=%s model=%s has_image=%s",
            session_id,
            self.model,
            bool(image_base64),
        )
        from app.services import provider_activity

        with provider_activity.Track(
            "gemini-stylist", {"model": self.model, "has_image": bool(image_base64)}
        ):
            raw = await chat.send_message(message)
        return _parse_json(raw)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(raw: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw  # defensive
    text = raw or ""
    # Strip ```json fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                logger.error("Gemini returned non-JSON: %s", exc)
        return {
            "reasoning_summary": "Parser could not decode model output.",
            "outfit_recommendations": [],
            "shopping_suggestions": [],
            "do_dont": [],
            "spoken_reply": text[:400],
            "_raw": text,
        }


def image_bytes_to_base64(img: bytes) -> str:
    return base64.b64encode(img).decode("ascii")


gemini_stylist_service = (
    GeminiStylistService() if settings.EMERGENT_LLM_KEY else None
)
