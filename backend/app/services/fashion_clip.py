"""FashionCLIP embedding service.

Runs **locally** inside the backend because FashionCLIP isn't routed via
HF Inference Providers. The CLIP model weights (~600MB) are downloaded
once on first use and cached under the HuggingFace cache directory.

Usage
-----
>>> from app.services.fashion_clip import fashion_clip_service
>>> vec = await fashion_clip_service.embed_image(image_bytes)          # 512-d
>>> vec = await fashion_clip_service.embed_text("cream linen blazer")  # 512-d
>>> score = fashion_clip_service.cosine(a, b)                          # float

All embeddings are already L2-normalised; cosine similarity is therefore
the same as a dot product. Callers can persist the 512-float vector
directly on the closet item / listing doc and later use it for
similarity search.

Phase A surface
---------------
* ``embed_image(bytes)``  -> 512-float list (L2-normalised)
* ``embed_text(str)``     -> 512-float list (L2-normalised)
* ``cosine(a, b)``        -> -1..1 float

These cover closet search and marketplace "items like this" today.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from functools import lru_cache
from typing import Any

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)


# Heavy imports are lazy so the backend boots even when torch isn't
# installed or the model repo is unreachable.
def _lazy_imports() -> tuple[Any, Any, Any, Any]:
    import numpy as np  # type: ignore
    import torch  # type: ignore
    from PIL import Image  # type: ignore
    from transformers import CLIPModel, CLIPProcessor  # type: ignore

    return np, torch, Image, (CLIPModel, CLIPProcessor)


class FashionClipService:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self._model: Any = None
        self._processor: Any = None
        self._device: str = "cpu"
        self._load_lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            t0 = time.perf_counter()

            def _load() -> tuple[Any, Any, str]:
                np, torch, Image, (CLIPModel, CLIPProcessor) = _lazy_imports()
                dev = "cuda" if torch.cuda.is_available() else "cpu"
                mdl = CLIPModel.from_pretrained(self.model_id)
                mdl.eval().to(dev)
                proc = CLIPProcessor.from_pretrained(self.model_id)
                return mdl, proc, dev

            try:
                self._model, self._processor, self._device = await asyncio.to_thread(_load)
            except Exception as exc:  # noqa: BLE001
                logger.exception("FashionCLIP load failed: %s", exc)
                raise
            logger.info(
                "FashionCLIP loaded model=%s device=%s in %.1fs",
                self.model_id,
                self._device,
                time.perf_counter() - t0,
            )

    # ------------------------------------------------------------------ API
    async def embed_image(self, image_bytes: bytes) -> list[float]:
        await self._ensure_loaded()
        t0 = time.perf_counter()
        ok = False
        err: str | None = None
        try:
            def _run() -> list[float]:
                np, torch, Image, _ = _lazy_imports()
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                inputs = self._processor(images=img, return_tensors="pt").to(self._device)
                with torch.inference_mode():
                    out = self._model.get_image_features(**inputs)
                    # transformers 5.x returns a ModelOutput with
                    # .pooler_output; older versions returned a tensor.
                    feats = getattr(out, "pooler_output", out)
                    feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
                return feats.cpu().numpy().astype("float32")[0].tolist()

            vec = await asyncio.to_thread(_run)
            ok = True
            return vec
        except Exception as exc:  # noqa: BLE001
            err = repr(exc)
            raise
        finally:
            provider_activity.record(
                "fashion-clip",
                ok=ok,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=err,
                extra={"model": self.model_id, "kind": "image"},
            )

    async def embed_text(self, text: str) -> list[float]:
        await self._ensure_loaded()
        text = (text or "").strip()
        if not text:
            return []
        t0 = time.perf_counter()
        ok = False
        err: str | None = None
        try:
            def _run() -> list[float]:
                np, torch, Image, _ = _lazy_imports()
                inputs = self._processor(
                    text=[text], return_tensors="pt", padding=True, truncation=True
                ).to(self._device)
                with torch.inference_mode():
                    out = self._model.get_text_features(**inputs)
                    feats = getattr(out, "pooler_output", out)
                    feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
                return feats.cpu().numpy().astype("float32")[0].tolist()

            vec = await asyncio.to_thread(_run)
            ok = True
            return vec
        except Exception as exc:  # noqa: BLE001
            err = repr(exc)
            raise
        finally:
            provider_activity.record(
                "fashion-clip",
                ok=ok,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=err,
                extra={"model": self.model_id, "kind": "text"},
            )

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        # Both vectors are already L2-normalised \u2192 cosine == dot product.
        dot = 0.0
        for x, y in zip(a, b):
            dot += x * y
        return float(dot)


@lru_cache(maxsize=1)
def _get_service() -> FashionClipService | None:
    if not settings.FASHION_CLIP_ENABLED:
        return None
    try:
        # Don't download at import time \u2014 the service loads lazily on first call.
        return FashionClipService(settings.FASHION_CLIP_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FashionCLIP service unavailable: %s", exc)
        return None


fashion_clip_service: FashionClipService | None = _get_service()
