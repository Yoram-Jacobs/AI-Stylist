"""Eyes v3 (Gemma 4 E2B) local GGUF runtime — Phase Z6 deliverable.

Loads the Q4_K_M language-model GGUF + F16 mmproj as a singleton
``llama_cpp.Llama`` instance and exposes one async API:

    raw = await chat_completion(system_prompt, user_text, image_b64_jpeg, ...)

That `raw` is the model's untrimmed text response — pipe it through
``parse_eyes_response`` to get a dict (single garment) or list[dict]
(multi-garment, when the prompt asks for every garment in the image).

Why local GGUF instead of the HF Space we've been routing through?

* **Cost**: a 5 GB on-disk model on a Hetzner CPX31 (~$15/mo) replaces an
  always-on HF Space (~$0.06/h GPU = $43/mo idle) at ~equivalent latency
  for our backend-call usage pattern (8–15 s/photo).
* **Privacy**: garment uploads never leave the VPS.
* **Offline / on-device**: the same GGUF pair (Q4_K_M + mmproj-F16) is the
  artifact we ship to mobile (via the Capacitor wrap on the roadmap).

Required env vars (defaults shown):

    EYES_GEMMA_LOCAL_LM_PATH       /var/models/eyes_v3/Eyes_v3_Gemma4_E2B-Q4_K_M.gguf
    EYES_GEMMA_LOCAL_MMPROJ_PATH   /var/models/eyes_v3/Eyes_v3_Gemma4_E2B-mmproj-F16.gguf
    EYES_GEMMA_LOCAL_N_GPU_LAYERS  0          # CPU-only VPS; set to 99 if you ever GPU-attach
    EYES_GEMMA_LOCAL_N_CTX         4096
    EYES_GEMMA_LOCAL_N_THREADS     0          # 0 = autodetect (= os.cpu_count())
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ── Configuration (env-overridable) ──────────────────────────────────
_LM_PATH = Path(os.environ.get(
    "EYES_GEMMA_LOCAL_LM_PATH",
    "/var/models/eyes_v3/Eyes_v3_Gemma4_E2B-Q4_K_M.gguf",
))
_MMPROJ_PATH = Path(os.environ.get(
    "EYES_GEMMA_LOCAL_MMPROJ_PATH",
    "/var/models/eyes_v3/Eyes_v3_Gemma4_E2B-mmproj-F16.gguf",
))
_N_GPU_LAYERS = int(os.environ.get("EYES_GEMMA_LOCAL_N_GPU_LAYERS", "0"))
_N_CTX = int(os.environ.get("EYES_GEMMA_LOCAL_N_CTX", "4096"))
_N_THREADS = int(os.environ.get("EYES_GEMMA_LOCAL_N_THREADS", "0")) or (os.cpu_count() or 4)

# ── Singleton model handle ───────────────────────────────────────────
_model: Any = None              # llama_cpp.Llama instance
_handler: Any = None            # the mtmd image chat handler
_lock = threading.Lock()
_ready: bool = False


def is_available() -> bool:
    """Cheap probe — both artifact files exist on disk."""
    return _LM_PATH.exists() and _MMPROJ_PATH.exists()


def _get_model() -> Any:
    """Lazy-load the GGUF pair on first request. Thread-safe singleton."""
    global _model, _handler, _ready
    if _ready:
        return _model
    with _lock:
        if _ready:
            return _model
        if not is_available():
            raise RuntimeError(
                f"Eyes v3 GGUF not found: LM={_LM_PATH} (exists={_LM_PATH.exists()}), "
                f"mmproj={_MMPROJ_PATH} (exists={_MMPROJ_PATH.exists()})"
            )
        # Import here so the module loads even on hosts without llama-cpp-python
        # (e.g. preview pods where this provider is never selected).
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Llava15ChatHandler  # mtmd handler base

        log.info(
            "loading Eyes v3 Gemma4 GGUF: LM=%.2f GB + mmproj=%.0f MB "
            "(n_ctx=%d, n_threads=%d, n_gpu_layers=%d)",
            _LM_PATH.stat().st_size / 1e9,
            _MMPROJ_PATH.stat().st_size / 1e6,
            _N_CTX, _N_THREADS, _N_GPU_LAYERS,
        )
        t0 = time.perf_counter()
        _handler = Llava15ChatHandler(clip_model_path=str(_MMPROJ_PATH), verbose=False)
        _model = Llama(
            model_path=str(_LM_PATH),
            chat_handler=_handler,
            chat_format="gemma",            # uses tokenizer's bundled Jinja
            n_ctx=_N_CTX,
            n_threads=_N_THREADS,
            n_gpu_layers=_N_GPU_LAYERS,
            verbose=False,
        )
        log.info("Eyes v3 ready in %.1fs", time.perf_counter() - t0)
        _ready = True
        return _model


# ── Public API ───────────────────────────────────────────────────────
async def chat_completion(
    *,
    system_prompt: str,
    user_text: str,
    image_b64_jpeg: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: float = 60.0,
) -> str:
    """Async wrapper around the (synchronous) llama-cpp-python call.

    Returns the raw model output text (may contain a <|channel>thought
    trace prefix — strip via :func:`parse_eyes_response`).
    """
    def _sync_call() -> str:
        model = _get_model()
        image_url = f"data:image/jpeg;base64,{image_b64_jpeg}"
        resp = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": user_text},
                ]},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp["choices"][0]["message"]["content"] or ""

    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _sync_call),
        timeout=timeout,
    )


# ── Response parser (also used by the prod garment_vision.parse_response path) ──
_THOUGHT_DELIM = "<channel|>"
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_eyes_response(raw: str) -> dict | list[dict]:
    """Strip Gemma 4 thinking trace and parse the trailing JSON.

    Returns:
        * dict — single-garment response (current production prompt)
        * list[dict] — multi-garment response (when prompt asks for every garment)

    Raises:
        ValueError — no parseable JSON in the response (typically means
        the thought trace ate the entire token budget; caller should
        bump max_tokens and retry, or fall back to Gemini).
    """
    if _THOUGHT_DELIM in raw:
        raw = raw.split(_THOUGHT_DELIM, 1)[1]
    raw = raw.strip()
    # Prefer array (multi-garment) over object (single)
    for rx in (_ARRAY_RE, _OBJECT_RE):
        m = rx.search(raw)
        if m:
            return json.loads(m.group(0))
    raise ValueError(f"no JSON in Eyes v3 response (first 300 chars): {raw[:300]!r}")
