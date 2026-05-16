"""Heavy-model warmup orchestrator (Patch M13 — May 2026).

Why this module exists
----------------------
The three heavy CV models that gate the `/api/v1/closet/analyze`
pipeline — SegFormer (clothing parser), rembg (background matte), and
FashionCLIP (faithfulness guard) — were each individually lazy-loaded
on their first invocation. On a cold backend, that meant the FIRST
user upload paid the cumulative model-init cost:

    SegFormer ~5-8s + rembg ~1-3s + CLIP ~3-8s = 9-19s of cold tax

…ON TOP of Gemini detection + per-crop Gemini analysis. The Kubernetes
ingress front of the preview / Emergent pods has a hard 60 s upstream
timeout. Combined with a 4K outfit upload of an outfit with 5+ items
that's analysed per-crop, the cold-start total regularly exceeded the
ceiling and the ingress returned **502 Bad Gateway** to the browser.
The user retried, models were now warm, second attempt succeeded —
which is exactly the "Analysis failed on first attempt, works on
retry" UX bug filed as Issue 3.

Strategy
--------
Fire-and-forget asyncio task from the FastAPI startup hook. The task:

  1. Doesn't block app startup (supervisor / k8s readiness probe stays
     happy — backend reports ready in <3 s as before).
  2. Loads SegFormer + rembg + CLIP **in parallel** (each on its own
     worker thread via ``asyncio.to_thread``) so the warm-up wall time
     is ``max(load_segformer, load_rembg, load_clip)`` rather than
     their sum. On the dev pod the parallel total clocks ~6 s versus
     ~14 s serial.
  3. Re-uses the existing lazy-singleton locks inside each service, so
     if a real user request races the warmup, neither side double-
     loads — both threads block on the same shared lock and the first
     one to win publishes the singleton.

Kill switch
-----------
``settings.WARMUP_MODELS_ON_STARTUP`` (env var of the same name).
Default ``true`` when the local-ML stack is enabled, ``false`` on
lightweight deploys (LIGHTWEIGHT_DEPLOY=true) where the pod can't
afford to preload these models at all (250m CPU / 1Gi RAM Emergent
host pod). The lightweight path uses the Gemini-only detect path so
SegFormer/rembg/CLIP are never actually needed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


async def _warm_segformer() -> tuple[str, bool, float, str]:
    """Force the SegFormer singleton to load on a worker thread.

    Returns ``(name, ok, seconds, detail)`` for the audit log.
    """
    if not settings.USE_LOCAL_CLOTHING_PARSER:
        return ("segformer", False, 0.0, "skipped: USE_LOCAL_CLOTHING_PARSER=false")
    t0 = time.perf_counter()
    try:
        from app.services import clothing_parser

        await asyncio.to_thread(clothing_parser._load_model)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return (
            "segformer",
            False,
            time.perf_counter() - t0,
            f"FAILED: {type(exc).__name__}: {str(exc)[:200]}",
        )
    return ("segformer", True, time.perf_counter() - t0, "ready")


async def _warm_rembg() -> tuple[str, bool, float, str]:
    """Force the rembg session to materialise on a worker thread."""
    if not settings.AUTO_MATTE_CROPS:
        return ("rembg", False, 0.0, "skipped: AUTO_MATTE_CROPS=false")
    t0 = time.perf_counter()
    try:
        from app.services import background_matting

        await asyncio.to_thread(background_matting._get_session)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return (
            "rembg",
            False,
            time.perf_counter() - t0,
            f"FAILED: {type(exc).__name__}: {str(exc)[:200]}",
        )
    return ("rembg", True, time.perf_counter() - t0, "ready")


async def _warm_fashion_clip() -> tuple[str, bool, float, str]:
    """Force the FashionCLIP service to download/load weights.

    CLIP is the optional faithfulness guard for the rembg matte. If it
    fails to load we simply log and continue — the matte pipeline still
    works without it (the guard becomes a no-op).
    """
    t0 = time.perf_counter()
    try:
        from app.services import fashion_clip

        svc: Any = fashion_clip._get_service()  # noqa: SLF001
        if svc is None:
            return (
                "fashion_clip",
                False,
                0.0,
                "skipped: FashionCLIP service unavailable",
            )
        await svc._ensure_loaded()  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        return (
            "fashion_clip",
            False,
            time.perf_counter() - t0,
            f"FAILED: {type(exc).__name__}: {str(exc)[:200]}",
        )
    return ("fashion_clip", True, time.perf_counter() - t0, "ready")


async def warmup_models() -> None:
    """Parallel warm-load entry point.

    Designed to be invoked as ``asyncio.create_task(warmup_models())``
    from the FastAPI startup hook — NEVER ``await``-ed inline. The task
    runs to completion in the background; if it crashes we log and
    drop, because every dependent service still has a lazy fallback.
    """
    if not settings.WARMUP_MODELS_ON_STARTUP:
        logger.info(
            "warmup_models: skipped (WARMUP_MODELS_ON_STARTUP=false)"
        )
        return

    t_wall_start = time.perf_counter()
    logger.info(
        "warmup_models: starting parallel warmup of SegFormer + rembg "
        "+ FashionCLIP (kill-switch: WARMUP_MODELS_ON_STARTUP=false)"
    )

    # Patch M13.1 — pre-import the `transformers` symbols on the main
    # thread BEFORE we fan out to worker threads. The HuggingFace
    # ``transformers`` package uses a lazy ``__getattr__`` on its
    # top-level ``__init__.py`` to defer importing the ~thousand
    # model classes until first reference. That mechanism is NOT
    # thread-safe: when SegFormer and CLIP warmups race to do
    # ``from transformers import X`` simultaneously, one of them
    # observes a half-initialised module and raises
    # ``ImportError: cannot import name 'CLIPModel' from
    # 'transformers'``. Doing the imports here serialises the lazy
    # loader once on the asyncio thread; the parallel worker threads
    # below then only touch already-resolved class references.
    try:
        from transformers import (  # noqa: F401
            CLIPModel,
            CLIPProcessor,
            SegformerForSemanticSegmentation,
            SegformerImageProcessor,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "warmup_models: transformers pre-import skipped (%s) — "
            "individual warmups will retry on their own threads",
            repr(exc)[:160],
        )

    try:
        # Patch M13.3 — Sequence SegFormer → FashionCLIP serially on a
        # single transformers track, parallel with rembg on its own
        # track. Both SegFormer and FashionCLIP go through the same
        # `transformers` ``from_pretrained`` machinery; running them in
        # concurrent worker threads exposes a torch/accelerate race
        # (one thread observes a meta-device model and ``.to(dev)``
        # raises ``NotImplementedError: Cannot copy out of meta
        # tensor``). rembg uses onnxruntime and is fully independent,
        # so it stays parallel. Wall time on the dev pod:
        #     SegFormer 0.8s + CLIP ~1.5s = 2.3s, max(2.3, rembg 0.7) = 2.3s
        # vs the old serial 3.0s; the parallel-of-three attempt was
        # 3.7s wall and dropped CLIP entirely. This is the resilient
        # middle ground.
        async def _warm_transformers_track() -> list[tuple[str, bool, float, str]]:
            r1 = await _warm_segformer()
            r2 = await _warm_fashion_clip()
            return [r1, r2]

        transformers_track, rembg_result = await asyncio.gather(
            _warm_transformers_track(),
            _warm_rembg(),
            return_exceptions=False,
        )
        results = [*transformers_track, rembg_result]
    except Exception as exc:  # noqa: BLE001
        # Belt-and-braces — every helper catches its own exceptions and
        # returns a tuple; an exception here means something escaped.
        logger.exception("warmup_models: unexpected fatal exception: %s", exc)
        return

    wall = time.perf_counter() - t_wall_start
    ok_count = sum(1 for r in results if r[1])
    failed = [r for r in results if not r[1] and not r[3].startswith("skipped")]
    skipped = [r for r in results if r[3].startswith("skipped")]

    for name, ok, secs, detail in results:
        if ok:
            logger.info(
                "warmup_models: %s ready in %.2fs",
                name, secs,
            )
        elif detail.startswith("skipped"):
            logger.info("warmup_models: %s %s", name, detail)
        else:
            logger.warning(
                "warmup_models: %s did NOT warm in %.2fs (%s) — lazy "
                "fallback will load on first hit",
                name, secs, detail,
            )

    logger.info(
        "warmup_models: complete in %.2fs wall (%d/%d ready, %d failed, "
        "%d skipped) — first /closet/analyze should now stay under the "
        "60s ingress ceiling",
        wall,
        ok_count,
        len(results),
        len(failed),
        len(skipped),
    )
