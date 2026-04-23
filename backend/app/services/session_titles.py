"""Generate short, friendly titles for stylist conversations.

Uses the Emergent LLM key + Gemini Flash so it's cheap and quick. Falls back
to a rule-based truncation if the LLM is unreachable so we never block the
user's first turn.
"""
from __future__ import annotations

import logging
import re
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage

from app.config import settings

logger = logging.getLogger(__name__)

_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "he": "Hebrew",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "hi": "Hindi",
}


def _fallback_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return "New conversation"
    words = cleaned.split()
    return " ".join(words[:5])[:60]


async def generate_session_title(text: str, language: str = "en") -> str:
    """Return a crisp 3–5 word conversation title based on the first user turn."""
    text = (text or "").strip()
    if not text:
        return "New conversation"
    api_key = settings.EMERGENT_LLM_KEY
    if not api_key:
        return _fallback_title(text)

    lang_code = (language or "en").lower()
    lang_name = _LANG_NAMES.get(lang_code, "English")
    system_msg = (
        "You summarise a user's stylist question into a very short thread "
        f"title in {lang_name}. Return ONLY the title — no quotes, no "
        "punctuation at the ends, no emoji, 3 to 5 words, Title Case where "
        "the target language uses it. Do NOT prefix with words like 'Topic:' "
        "or 'Title:'."
    )
    chat = LlmChat(
        api_key=api_key,
        session_id=f"title-{uuid.uuid4().hex[:10]}",
        system_message=system_msg,
    )
    chat.with_model(
        settings.DEFAULT_STYLIST_PROVIDER,
        # Flash is more than enough for a 5-word summary.
        "gemini-2.5-flash",
    )
    try:
        raw = await chat.send_message(UserMessage(text=text[:400]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session title generation failed: %s", exc)
        return _fallback_title(text)

    title = (raw or "").strip()
    # Strip surrounding quotes / brackets if the model added them
    title = title.strip(" \t\n\r\"'`“”‘’[](){}")
    # If the model returned multiple lines, keep the first
    title = title.splitlines()[0].strip() if title else ""
    if not title:
        return _fallback_title(text)
    # Hard cap at 60 chars as a safety net
    return title[:60]
