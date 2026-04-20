"""Deepgram Aura-2 Text-to-Speech — REST + WebSocket streaming helpers.

REST helper `speak_to_bytes` is used in the POC and for batch saves.
WebSocket helper `stream_speak` forwards text -> Deepgram -> byte chunks so the
stylist agent can speak while the LLM is still emitting deltas.

Deepgram’s v6 SDK exposes HTTPX transport for REST and a websocket client for
streaming. We only use the minimal subset required for Phase 1 POC and keep
the streaming helper self-contained so it can be wired to FastAPI WebSockets
in Phase 2 / 3.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx
import websockets

from app.config import settings

logger = logging.getLogger(__name__)


DEEPGRAM_REST_URL = "https://api.deepgram.com/v1/speak"
DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/speak"


class DeepgramService:
    def __init__(self) -> None:
        if not settings.DEEPGRAM_API_KEY:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")
        self.api_key = settings.DEEPGRAM_API_KEY
        self.default_model = settings.DEFAULT_TTS_MODEL
        self.default_encoding = settings.DEFAULT_TTS_ENCODING

    # -------------------- REST (batch) --------------------
    async def speak_to_bytes(
        self,
        text: str,
        voice: str | None = None,
        encoding: str | None = None,
    ) -> bytes:
        """Synthesise full text -> audio bytes (mp3/linear16/…)."""
        voice = voice or self.default_model
        encoding = encoding or self.default_encoding
        params = {"model": voice, "encoding": encoding}
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}
        from app.services import provider_activity

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with provider_activity.Track(
                "deepgram-tts", {"voice": voice, "encoding": encoding}
            ):
                resp = await client.post(
                    DEEPGRAM_REST_URL, params=params, headers=headers, json=payload
                )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Deepgram TTS failed {resp.status_code}: {resp.text[:300]}"
                    )
            logger.info(
                "Deepgram TTS ok voice=%s encoding=%s bytes=%d",
                voice,
                encoding,
                len(resp.content),
            )
            return resp.content

    # -------------------- WebSocket streaming --------------------
    async def stream_speak(
        self,
        text_iter: AsyncIterator[str],
        voice: str | None = None,
        encoding: str = "mp3",
        sample_rate: int = 24000,
    ) -> AsyncIterator[bytes]:
        """Stream synthesis: consume text chunks, yield audio bytes.

        We open a single WebSocket to Deepgram, push each text chunk as a
        `Speak` message, and relay every binary frame back to the caller.

        Usage:
            async for audio_chunk in deepgram.stream_speak(my_text_iter):
                await websocket.send_bytes(audio_chunk)
        """
        voice = voice or self.default_model
        url = (
            f"{DEEPGRAM_WS_URL}?model={voice}&encoding={encoding}&sample_rate={sample_rate}"
        )
        headers = [("Authorization", f"Token {self.api_key}")]

        async with websockets.connect(
            url, additional_headers=headers, max_size=None
        ) as ws:
            logger.info("Deepgram WS connected voice=%s", voice)

            async def _sender() -> None:
                try:
                    async for chunk in text_iter:
                        if not chunk:
                            continue
                        await ws.send(
                            json.dumps({"type": "Speak", "text": chunk})
                        )
                    await ws.send(json.dumps({"type": "Flush"}))
                    # give the server a beat to push final audio
                    await asyncio.sleep(0.1)
                    await ws.send(json.dumps({"type": "Close"}))
                except Exception as exc:  # noqa: BLE001
                    logger.error("Deepgram WS sender error: %s", exc)

            sender_task = asyncio.create_task(_sender())
            try:
                async for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        yield bytes(message)
                    else:
                        # Control message (Metadata / Flushed / Closed)
                        logger.debug("Deepgram WS ctrl: %s", message)
                        try:
                            payload = json.loads(message)
                            if payload.get("type") in {"Closed", "CloseStream"}:
                                break
                        except Exception:
                            pass
            finally:
                await sender_task


deepgram_service = DeepgramService() if settings.DEEPGRAM_API_KEY else None
