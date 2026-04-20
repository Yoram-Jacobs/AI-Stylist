"""Hugging Face image service \u2014 zero-cost generate + (synthesised) edit.

We swapped off Nano Banana when the Emergent proxy lost upstream access to
Google's image-generation endpoints. The Hugging Face Inference Providers
API exposes only text-to-image on the free ``hf-inference`` provider, so
"edit a garment" is implemented as a **prompt synthesis**: we describe the
target garment in detail, ask FLUX.1-schnell to render it, and store the
result as a new ``variants[]`` entry. The original photo is left untouched.

Public surface (signature-compatible with the previous ``gemini_image_service``):

* ``generate(prompt, ...)`` \u2014 pure text-to-image.
* ``edit(image, prompt, *, garment_metadata=None)`` \u2014 image + text.
  ``image`` is accepted for API compatibility but is NOT directly fed to
  the model; we extract its descriptive cues via ``garment_metadata`` if
  provided. This keeps the closet/edit + stylist/infill call sites
  unchanged while still delivering a useful editorial preview.

All callers receive ``{image_b64, mime_type, model_used, text}``.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import Any

import httpx
from huggingface_hub import InferenceClient

from app.config import settings

logger = logging.getLogger(__name__)


def _coerce_image_bytes(out: Any) -> bytes | None:
    """HF can return a PIL Image or raw bytes depending on the provider."""
    if out is None:
        return None
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    save = getattr(out, "save", None)
    if save:
        buf = io.BytesIO()
        try:
            save(buf, format="PNG", optimize=True)
            return buf.getvalue()
        except Exception:  # noqa: BLE001
            return None
    return None


class HFImageService:
    def __init__(self) -> None:
        if not settings.HF_TOKEN:
            raise RuntimeError("HF_TOKEN is not configured.")
        self.token = settings.HF_TOKEN
        self.model = settings.HF_IMAGE_MODEL
        self.provider = settings.HF_IMAGE_PROVIDER
        self._client = InferenceClient(
            api_key=self.token, timeout=120, provider=self.provider
        )

    # -------------------- public API --------------------
    async def generate(
        self, prompt: str, *, session_id: str | None = None
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._run_text_to_image, prompt)

    async def edit(
        self,
        image: bytes | str,
        prompt: str,
        *,
        garment_metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        synthesised = self._build_edit_prompt(prompt, garment_metadata)
        logger.info("HF edit prompt: %s", synthesised[:160])
        return await asyncio.to_thread(self._run_text_to_image, synthesised)

    # -------------------- internals --------------------
    def _run_text_to_image(self, prompt: str) -> dict[str, Any]:
        from app.services import provider_activity

        last_exc: Exception | None = None
        for attempt in range(3):
            t0 = time.time()
            try:
                with provider_activity.Track("hf-image", {"model": self.model}):
                    out = self._client.text_to_image(prompt=prompt, model=self.model)
                raw = _coerce_image_bytes(out)
                if not raw:
                    raise RuntimeError("HF text_to_image returned no bytes")
                logger.info(
                    "HF text_to_image OK (%s, %.1fs, %d bytes)",
                    self.model,
                    time.time() - t0,
                    len(raw),
                )
                return {
                    "image_b64": base64.b64encode(raw).decode("ascii"),
                    "mime_type": "image/png",
                    "model_used": self.model,
                    "text": "",
                }
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = repr(exc)
                transient = any(
                    tok in msg
                    for tok in ("503", "504", "timeout", "Timeout", "TimeoutException")
                )
                if not transient or attempt == 2:
                    raise
                wait = 1.5 * (2**attempt)
                logger.info(
                    "HF text_to_image transient error (attempt %d, sleeping %.1fs): %s",
                    attempt + 1,
                    wait,
                    msg[:160],
                )
                time.sleep(wait)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _build_edit_prompt(
        user_prompt: str, meta: dict[str, Any] | None
    ) -> str:
        """Compose a descriptive prompt from the item's metadata + user edit."""
        meta = meta or {}
        descriptor_bits: list[str] = []
        for key in ("color", "material", "pattern", "brand", "category", "title"):
            v = meta.get(key)
            if v:
                descriptor_bits.append(str(v))
        descriptor = ", ".join(descriptor_bits) if descriptor_bits else "garment"
        # Keep the user's edit instruction primary; the descriptor anchors the
        # shape so the generation stays close to the original piece.
        composed = (
            f"Editorial fashion photograph of a {descriptor}, but with the "
            f"following change: {user_prompt}. Studio lighting, plain neutral "
            "backdrop, garment-only product shot, sharp focus, photorealistic, "
            "no people, no text, no logos."
        )
        return composed[:1000]


# -------------------- shared helpers --------------------
async def _to_bytes(image: bytes | str) -> bytes:
    if isinstance(image, bytes):
        return image
    if image.startswith("data:"):
        return base64.b64decode(image.split(",", 1)[1])
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(image, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


hf_image_service = HFImageService() if settings.HF_TOKEN else None
