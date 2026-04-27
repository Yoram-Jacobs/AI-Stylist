"""Native Google Gemini image service — Nano Banana (gemini-2.5-flash-image).

Why this exists separately from `hf_image_service.py`:

* The Emergent proxy does not route image-generation traffic to Gemini, so
  we historically fell back to HF FLUX. With a direct ``GEMINI_API_KEY``
  configured, we can use Nano Banana — Google's GA image-gen / edit model
  optimised for fast, photorealistic, character-consistent product shots.
* This service is the preferred reconstructor when ``settings.has_native_gemini``
  is true. ``reconstruction.py`` falls back to HF FLUX otherwise.

Public surface (matches ``hf_image_service`` so callers can swap freely):

* ``generate(prompt) -> {image_b64, mime_type, model_used, text}``
* ``edit(image_bytes, prompt, *, garment_metadata=None) -> {...}``

Both calls are wrapped in ``asyncio.to_thread`` so they're safe inside a
FastAPI request without blocking the event loop.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# Lazy import of the SDK — keeps the rest of the codebase importable even
# when google-genai is not installed (CI / minimal images).
try:
    from google import genai as _genai  # type: ignore
    from google.genai import types as _genai_types  # type: ignore
except Exception as _exc:  # noqa: BLE001
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]
    logger.info("google-genai not importable: %s", _exc)


def _coerce_image_part(part: Any) -> bytes | None:
    """Extract image bytes from a Gemini response part."""
    inline = getattr(part, "inline_data", None)
    if inline is None:
        return None
    data = getattr(inline, "data", None)
    if not data:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    # Some SDK versions return base64-encoded strings.
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except Exception:  # noqa: BLE001
            return None
    return None


class GeminiImageService:
    """Thin async wrapper around `google-genai` for Nano Banana."""

    def __init__(self) -> None:
        if _genai is None:
            raise RuntimeError(
                "google-genai is not installed. Add `google-genai` to "
                "requirements.txt and reinstall."
            )
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Required for Nano Banana."
            )
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_IMAGE_MODEL
        # The SDK is sync — we instantiate a Client per service and call it
        # from a worker thread. The client is cheap and thread-safe.
        self._client = _genai.Client(api_key=self.api_key)

    # ------------------------------------------------------------------ public
    async def generate(
        self, prompt: str, *, session_id: str | None = None
    ) -> dict[str, Any]:
        """Pure text-to-image. Returns the same shape as HFImageService.generate."""
        return await asyncio.to_thread(self._run_generate, prompt, None)

    async def edit(
        self,
        image: bytes | str,
        prompt: str,
        *,
        garment_metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Image + text → image (the Wardrobe Reconstructor entry point).

        Composes a rich descriptive prompt out of the user's edit
        instruction + the garment metadata coming from The Eyes, then
        feeds the original crop alongside it so Nano Banana preserves
        fabric texture, pattern, and silhouette while only repairing
        the missing / clipped areas.
        """
        composed = self._build_edit_prompt(prompt, garment_metadata)
        image_bytes = await _to_bytes(image)
        return await asyncio.to_thread(self._run_generate, composed, image_bytes)

    # ------------------------------------------------------------------ internals
    def _run_generate(
        self,
        prompt: str,
        image_bytes: bytes | None,
    ) -> dict[str, Any]:
        from app.services import provider_activity

        last_exc: Exception | None = None
        for attempt in range(3):
            t0 = time.time()
            try:
                contents: list[Any] = [prompt]
                if image_bytes:
                    # Pass the source image as an inline Part so the model
                    # has the actual pixels to edit / outpaint from.
                    assert _genai_types is not None  # mypy
                    contents.append(
                        _genai_types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        )
                    )
                with provider_activity.Track(
                    "gemini-image",
                    {"model": self.model, "edit": bool(image_bytes)},
                ):
                    resp = self._client.models.generate_content(
                        model=self.model,
                        contents=contents,
                    )
                # Find the first inline image part.
                raw: bytes | None = None
                text_out = ""
                candidates = getattr(resp, "candidates", []) or []
                for cand in candidates:
                    parts = getattr(getattr(cand, "content", None), "parts", []) or []
                    for part in parts:
                        if raw is None:
                            raw = _coerce_image_part(part)
                        if raw is None:
                            txt = getattr(part, "text", None)
                            if txt:
                                text_out += str(txt)
                    if raw:
                        break
                if not raw:
                    raise RuntimeError(
                        "Gemini image response had no inline_data part "
                        f"(text='{text_out[:160]}')"
                    )
                logger.info(
                    "Nano Banana OK (%s, %.1fs, %d bytes, edit=%s)",
                    self.model,
                    time.time() - t0,
                    len(raw),
                    bool(image_bytes),
                )
                return {
                    "image_b64": base64.b64encode(raw).decode("ascii"),
                    "mime_type": "image/png",
                    "model_used": self.model,
                    "text": text_out,
                }
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = repr(exc)
                transient = any(
                    tok in msg
                    for tok in ("503", "504", "timeout", "Timeout", "TimeoutException", "RESOURCE_EXHAUSTED")
                )
                if not transient or attempt == 2:
                    logger.warning(
                        "Nano Banana failed (attempt %d, giving up): %s",
                        attempt + 1,
                        msg[:240],
                    )
                    raise
                wait = 1.5 * (2 ** attempt)
                logger.info(
                    "Nano Banana transient error (attempt %d, sleeping %.1fs): %s",
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
        meta = meta or {}
        descriptor_bits: list[str] = []
        for key in ("color", "material", "pattern", "brand", "category", "title"):
            v = meta.get(key)
            if v:
                descriptor_bits.append(str(v))
        descriptor = ", ".join(descriptor_bits) if descriptor_bits else "garment"
        composed = (
            f"Editorial fashion product photograph of a complete, full-length "
            f"{descriptor}. {user_prompt}. Studio lighting, plain off-white "
            "backdrop, garment-only product shot, centered composition, sharp "
            "focus, photorealistic, preserve fabric texture and pattern "
            "details, no people, no mannequin body, no text, no logos, "
            "no watermarks."
        )
        return composed[:1000]


# ----------------------------------------------------------------- helpers
async def _to_bytes(image: bytes | str) -> bytes:
    if isinstance(image, bytes):
        return image
    if image.startswith("data:"):
        return base64.b64decode(image.split(",", 1)[1])
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(image, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


# Module-level singleton — None when the direct Gemini key is absent so
# `reconstruction.py` can cleanly fall back to HF FLUX in dev preview.
gemini_image_service = (
    GeminiImageService() if (settings.has_native_gemini and _genai is not None) else None
)

if gemini_image_service is None:
    logger.info(
        "Nano Banana disabled (no GEMINI_API_KEY or google-genai missing). "
        "Image edits will fall back to HF FLUX where applicable."
    )
else:
    logger.info(
        "Nano Banana enabled — model=%s", gemini_image_service.model
    )
