"""Gemini 2.5 Flash Image (Nano Banana) generation + edit service.

Powered by the Emergent Universal LLM Key via ``emergentintegrations``. The
same key that drives the stylist brain (Gemini 2.5 Pro text) also grants
access to the image-generation models — no separate Google AI Studio key
required.

Public surface:

* ``generate(prompt, ...)`` — pure text-to-image (e.g. mood-board tiles for
  trend-scout, shopping suggestion mockups).
* ``edit(image, prompt, ...)`` — image-to-image edit with a textual
  instruction ("change this blazer to olive green", "make sleeves short").

Both return ``{image_b64, mime_type, model_used}``. We never log full base64
payloads — only the first 16 characters for trace context.
"""
from __future__ import annotations

import base64
import logging
import uuid
from typing import Any

import httpx
from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiImageService:
    def __init__(self) -> None:
        if not settings.EMERGENT_LLM_KEY:
            raise RuntimeError(
                "EMERGENT_LLM_KEY is not configured; Gemini image service unavailable."
            )
        self.api_key = settings.EMERGENT_LLM_KEY
        self.model = settings.GEMINI_IMAGE_MODEL

    # -------------------- public API --------------------
    async def generate(self, prompt: str, *, session_id: str | None = None) -> dict[str, Any]:
        """Text → image. Returns first image the model yields."""
        chat = self._fresh_chat(session_id)
        msg = UserMessage(text=prompt)
        return await self._run(chat, msg)

    async def edit(
        self,
        image: bytes | str,
        prompt: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Image + instruction → edited image.

        ``image`` may be raw bytes, a data-URL, or a remote URL (we download it).
        """
        raw = await _to_bytes(image)
        b64 = base64.b64encode(raw).decode("ascii")
        chat = self._fresh_chat(session_id)
        msg = UserMessage(text=prompt, file_contents=[ImageContent(b64)])
        return await self._run(chat, msg)

    # -------------------- internals --------------------
    def _fresh_chat(self, session_id: str | None) -> LlmChat:
        sid = session_id or f"dressapp-imgen-{uuid.uuid4().hex[:12]}"
        chat = LlmChat(
            api_key=self.api_key,
            session_id=sid,
            system_message=(
                "You are DressApp's Generative Vision engine. Return a single "
                "photoreal garment image matching the instruction. No text in "
                "the image unless explicitly asked."
            ),
        )
        chat.with_model("gemini", self.model).with_params(modalities=["image", "text"])
        return chat

    async def _run(self, chat: LlmChat, msg: UserMessage) -> dict[str, Any]:
        # The Emergent proxy occasionally returns 502 BadGateway for the image
        # models during upstream cold-start. Retry a handful of times with
        # exponential backoff so transient blips never reach the user.
        import asyncio as _asyncio

        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                text, images = await chat.send_message_multimodal_response(msg)
                if not images:
                    logger.warning(
                        "Gemini image model returned no image (text preview=%s)",
                        (text or "")[:120],
                    )
                    raise RuntimeError("Gemini image generation returned no image")
                first = images[0]
                return {
                    "image_b64": first["data"],
                    "mime_type": first.get("mime_type", "image/png"),
                    "model_used": self.model,
                    "text": (text or "")[:500],
                }
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg_str = repr(exc)
                transient = any(
                    tok in msg_str
                    for tok in ("502", "BadGateway", "RateLimit", "overloaded", "UNAVAILABLE")
                )
                if not transient or attempt == 3:
                    raise
                wait = 1.5 * (2**attempt)
                logger.info(
                    "Nano Banana transient error (attempt %d, sleeping %.1fs): %s",
                    attempt + 1,
                    wait,
                    msg_str[:160],
                )
                await _asyncio.sleep(wait)
        assert last_exc is not None
        raise last_exc


async def _to_bytes(image: bytes | str) -> bytes:
    if isinstance(image, bytes):
        return image
    if image.startswith("data:"):
        return base64.b64decode(image.split(",", 1)[1])
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(image, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


gemini_image_service = (
    GeminiImageService() if settings.EMERGENT_LLM_KEY else None
)
