"""fal.ai client: SAM-2 style segmentation + Stable Diffusion image-to-image.

We call fal.ai through its official async client. For segmentation we try the
SAM-2 auto-segment endpoint first; if it’s unavailable we fall back to
`fal-ai/imageutils/rembg` which reliably isolates the foreground garment.

All methods accept either a URL or raw bytes. Raw bytes are uploaded via
`fal_client.upload_async` which returns a temporary URL the model can fetch.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

import fal_client

from app.config import settings

logger = logging.getLogger(__name__)


class FalService:
    def __init__(self) -> None:
        if not settings.FAL_KEY:
            raise RuntimeError("FAL_KEY is not configured.")
        # The fal_client reads FAL_KEY from the environment at call time.
        os.environ["FAL_KEY"] = settings.FAL_KEY
        self.segmentation_model = settings.FAL_SEGMENTATION_MODEL
        self.segmentation_fallback = settings.FAL_SEGMENTATION_FALLBACK_MODEL
        self.infill_model = settings.FAL_INFILL_MODEL

    # -------------------- helpers --------------------
    async def _upload_if_bytes(self, image: str | bytes, filename: str = "image.jpg") -> str:
        if isinstance(image, str):
            return image
        # fal.ai CDN auth can 403 for certain key tiers. We use a base64 data
        # URL, which fal models accept directly up to a few MB.
        mime = "image/jpeg"
        head = image[:12]
        if head.startswith(b"\x89PNG"):
            mime = "image/png"
        elif head[:4] == b"RIFF" and image[8:12] == b"WEBP":
            mime = "image/webp"
        b64 = base64.b64encode(image).decode("ascii")
        return f"data:{mime};base64,{b64}"

    async def _submit(self, model: str, arguments: dict[str, Any]) -> dict[str, Any]:
        logger.info("fal.ai call model=%s", model)
        handler = await fal_client.submit_async(model, arguments=arguments)
        return await handler.get()

    # -------------------- segmentation --------------------
    async def segment_garment(self, image: str | bytes) -> dict[str, Any]:
        """Return `{image_url, model_used, raw}` with the isolated garment.

        We attempt SAM-2 first (if configured). On any error we fall back to
        `fal-ai/imageutils/rembg` so the pipeline never fully breaks.
        """
        image_url = await self._upload_if_bytes(image)

        # Attempt 1 — configured SAM-2 model
        try:
            args = {"image_url": image_url}
            result = await self._submit(self.segmentation_model, args)
            out_url = _extract_image_url(result)
            if out_url:
                return {
                    "image_url": out_url,
                    "model_used": self.segmentation_model,
                    "raw": result,
                }
            logger.warning("SAM-2 returned no image; falling back to rembg")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SAM-2 failed (%s); falling back to rembg", exc)

        # Attempt 2 — rembg
        result = await self._submit(
            self.segmentation_fallback, {"image_url": image_url}
        )
        out_url = _extract_image_url(result)
        return {
            "image_url": out_url,
            "model_used": self.segmentation_fallback,
            "raw": result,
        }

    # -------------------- infill / edit --------------------
    async def edit_garment(
        self,
        image: str | bytes,
        prompt: str,
        strength: float = 0.55,
        num_inference_steps: int = 20,
    ) -> dict[str, Any]:
        """Image-to-image edit (“change color to black”, “make sleeves long”)."""
        image_url = await self._upload_if_bytes(image)
        args: dict[str, Any] = {
            "image_url": image_url,
            "prompt": prompt,
            "strength": strength,
            "num_inference_steps": num_inference_steps,
        }
        result = await self._submit(self.infill_model, args)
        out_url = _extract_image_url(result)
        return {"image_url": out_url, "model_used": self.infill_model, "raw": result}


def _extract_image_url(result: dict[str, Any]) -> str | None:
    """fal endpoints return images in several shapes; normalise here."""
    if not isinstance(result, dict):
        return None
    if "image" in result and isinstance(result["image"], dict):
        u = result["image"].get("url")
        if u:
            return u
    if "images" in result and isinstance(result["images"], list) and result["images"]:
        first = result["images"][0]
        if isinstance(first, dict):
            return first.get("url")
    # rembg style: {"image": {"url": ...}} already handled above.
    # Flux sometimes returns {"image": "https://..."}
    if isinstance(result.get("image"), str):
        return result["image"]
    return None


fal_service = FalService() if settings.FAL_KEY else None
