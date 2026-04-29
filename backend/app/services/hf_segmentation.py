"""Hugging Face segmentation service — zero-cost garment cutout.

Implementation notes
--------------------

The legacy ``api-inference.huggingface.co/models/<id>`` URL was retired by
Hugging Face in favour of the Inference Providers router. We therefore use
``huggingface_hub.InferenceClient``, which transparently resolves the best
provider for each model and handles auth + retries.

Model choice
~~~~~~~~~~~~

``facebook/sam-vit-base`` (pure Segment Anything) is no longer reachable on
the free serverless tier at time of writing. For our specific use case —
"cut out the clothing piece from a user-supplied photo" — a task-specific
clothing segmenter delivers higher quality at zero cost:

* **Primary:** ``mattmdjaga/segformer_b2_clothes`` — returns a mask per
  clothing category (upper-clothes, dress, skirt, pants, outerwear, ...).
  We compose the garment mask by unioning every non-human / non-background
  label.
* **Fallback:** plain return of the original image if the serverless
  endpoint is cold / rate-limited, so the closet upload path never fails.

Public surface (unchanged for callers):

* ``segment_garment(image) -> {image_b64, mime_type, model_used}`` where
  ``image_b64`` is a transparent-background PNG of the isolated garment.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

import httpx
import numpy as np
from huggingface_hub import InferenceClient
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# Labels in segformer_b2_clothes that we want to KEEP as "garment" pixels.
# We explicitly exclude body parts, hair, face, etc. so the cutout only
# contains fabric.
_GARMENT_LABELS = {
    "Hat",
    "Sunglasses",
    "Upper-clothes",
    "Skirt",
    "Pants",
    "Dress",
    "Belt",
    "Left-shoe",
    "Right-shoe",
    "Bag",
    "Scarf",
}


class HFSegmentationService:
    def __init__(self) -> None:
        if not settings.HF_TOKEN:
            raise RuntimeError("HF_TOKEN is not configured.")
        self.token = settings.HF_TOKEN
        # Primary model used by the InferenceClient path. HF_SAM_MODEL is kept
        # as a config surface so we can swap back to true SAM once Hugging
        # Face re-enables it on the free tier.
        self.primary_model = settings.HF_SAM_MODEL
        self._client = InferenceClient(api_key=self.token, timeout=60)

    # -------------------- public API --------------------
    async def segment_garment(self, image: bytes | str) -> dict[str, Any]:
        raw = await _to_bytes(image)

        try:
            return await asyncio.to_thread(self._run_segformer, raw)
        except Exception as exc:  # noqa: BLE001
            # Demote 402 (HF Router started charging in 2025) to debug —
            # the local SegFormer parser in clothing_parser.py is the
            # primary path now, so this is an expected fallback miss
            # rather than an alert-worthy failure.
            err_repr = repr(exc)
            is_paywall = "402" in err_repr or "Payment Required" in err_repr
            log = logger.debug if is_paywall else logger.warning
            log(
                "HF clothing segmenter failed (%s); returning original image",
                err_repr[:180],
            )
            return {
                "image_b64": base64.b64encode(raw).decode("ascii"),
                "mime_type": "image/jpeg",
                "model_used": "passthrough",
            }

    # -------------------- internals --------------------
    def _run_segformer(self, image_bytes: bytes) -> dict[str, Any]:
        from app.services import provider_activity

        # The HF Inference client expects a URL or a local path when given
        # raw bytes without an explicit content-type. We write to a secure
        # temp file to keep the API happy and avoid content-type guesswork.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tf:
            tf.write(image_bytes)
            tf.flush()
            with provider_activity.Track("hf-segformer", {"model": self.primary_model}):
                segments = self._client.image_segmentation(
                    image=tf.name, model=self.primary_model
                )
        if not segments:
            raise RuntimeError("segmenter returned no segments")

        src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = src.size
        garment_mask = np.zeros((h, w), dtype=bool)
        hits = []
        for seg in segments:
            label = getattr(seg, "label", None) or (
                seg.get("label") if isinstance(seg, dict) else None
            )
            mask_img = getattr(seg, "mask", None) or (
                seg.get("mask") if isinstance(seg, dict) else None
            )
            if not label or mask_img is None or label not in _GARMENT_LABELS:
                continue
            if not isinstance(mask_img, Image.Image):
                # Sometimes returned as base64 PNG string.
                try:
                    mask_img = Image.open(io.BytesIO(base64.b64decode(mask_img)))
                except Exception:  # noqa: BLE001
                    continue
            m = np.array(mask_img.convert("L").resize((w, h))) > 127
            if m.any():
                garment_mask |= m
                hits.append(label)

        if not garment_mask.any():
            raise RuntimeError("no garment labels detected in segmentation output")

        alpha = Image.fromarray((garment_mask.astype(np.uint8) * 255), mode="L")
        cutout = src.copy()
        cutout.putalpha(alpha)
        buf = io.BytesIO()
        cutout.save(buf, format="PNG", optimize=True)
        logger.info(
            "HF segmenter picked labels=%s (%d pixels kept)",
            hits,
            int(garment_mask.sum()),
        )
        return {
            "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "mime_type": "image/png",
            "model_used": self.primary_model,
        }


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


hf_segmentation_service = (
    HFSegmentationService() if settings.HF_TOKEN else None
)
