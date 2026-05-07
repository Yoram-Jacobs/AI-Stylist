"""DressApp Eyes — HF Space FastAPI service.

Phase 1 scope (Q4_K_M, no mmproj):
  * ``POST /predict`` — text-completion against the fine-tuned
    Gemma-4 E2B. Accepts an OpenAI-style chat list OR a single
    ``prompt`` string and optional ``system`` prompt; returns the
    assistant text plus token usage. The ``image_b64`` field is
    accepted for forward-compat but ignored when ``LLAMA_MMPROJ_PATH``
    is not set — the response carries a ``vision_disabled: true``
    flag so callers know.
  * ``GET  /healthz`` — 200 once the model is loaded; used by the HF
    Space health-check and by the backend's circuit breaker.
  * ``GET  /``        — banner + capability flags for human inspection.

Phase 2 (when an mmproj-*.gguf is uploaded to the model repo):
  * Set ``LLAMA_MMPROJ_PATH`` to the downloaded file. The code below
    auto-switches to ``Llava15ChatHandler`` and starts consuming
    ``image_b64`` as a real vision input — no API change required on
    the backend.

Designed for the free CPU Basic tier: the model is loaded once at
startup (~30 s) and reused for every request. Inference is single-
threaded against the shared context, so concurrency is gated by an
``asyncio.Lock`` to avoid corrupt KV-cache state when two callers
overlap.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dressapp-eyes")

MODEL_PATH = os.environ.get("LLAMA_MODEL_PATH", "/models/phase6-Q4_K_M.gguf")
MMPROJ_PATH = os.environ.get("LLAMA_MMPROJ_PATH")  # set in Phase 2
N_THREADS = int(os.environ.get("LLAMA_THREADS", "2"))
N_CTX = int(os.environ.get("LLAMA_CTX_SIZE", "4096"))
N_BATCH = int(os.environ.get("LLAMA_N_BATCH", "256"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the GGUF once at startup. Stored on ``app.state`` so we
    don't reach for module globals during testing."""
    from llama_cpp import Llama

    log.info(
        "loading model: %s (threads=%d ctx=%d)",
        MODEL_PATH, N_THREADS, N_CTX,
    )
    t0 = time.time()

    chat_handler = None
    vision_enabled = False
    if MMPROJ_PATH and os.path.isfile(MMPROJ_PATH):
        # Phase 2: pair the LLM with a real vision projector.
        from llama_cpp.llama_chat_format import Llava15ChatHandler

        log.info("vision projector found: %s", MMPROJ_PATH)
        chat_handler = Llava15ChatHandler(clip_model_path=MMPROJ_PATH)
        vision_enabled = True
    elif MMPROJ_PATH:
        # Misconfigured: env points to a missing file. Fail loud at
        # startup so the Space's health check never reports green.
        raise RuntimeError(
            f"LLAMA_MMPROJ_PATH set but not a file: {MMPROJ_PATH}"
        )

    # Pre-flight: surface a clear error if the GGUF didn't actually
    # land on disk or got truncated mid-download. llama.cpp's own
    # error ("Failed to load model from file") is uselessly opaque.
    try:
        _size = os.path.getsize(MODEL_PATH)
    except OSError as exc:
        raise RuntimeError(f"GGUF missing at {MODEL_PATH}: {exc}") from exc
    if _size < 100 * 1024 * 1024:  # any real LLM GGUF is >100 MB
        raise RuntimeError(
            f"GGUF at {MODEL_PATH} is only {_size} bytes — likely a "
            f"truncated download or LFS pointer file. Re-pull the repo."
        )
    log.info("gguf size: %.2f GB", _size / (1024**3))

    # ``chat_format='gemma'`` is the templating used by the Gemma-3 /
    # Gemma-4 E2B family. It's only consulted on the text path; when
    # ``chat_handler`` is set (Phase 2 vision), the handler owns
    # templating and this kwarg is ignored.
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_batch=N_BATCH,
        chat_handler=chat_handler,
        chat_format="gemma" if chat_handler is None else None,
        # Free CPU tier: no mmap is faster on HF's shared storage.
        use_mmap=False,
        use_mlock=False,
        verbose=False,
        # logits_all=False saves a chunk of RAM we don't need.
        logits_all=False,
    )
    _app.state.llm = llm
    _app.state.lock = asyncio.Lock()
    _app.state.vision_enabled = vision_enabled
    _app.state.loaded_at = time.time()
    log.info(
        "model ready in %.1fs (vision=%s)",
        time.time() - t0, vision_enabled,
    )
    try:
        yield
    finally:
        log.info("shutdown")


app = FastAPI(
    title="DressApp Eyes",
    version="phase1-q4km",
    description="Self-hosted fine-tuned Gemma-4 E2B for garment analysis.",
    lifespan=lifespan,
)


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class PredictIn(BaseModel):
    """Request body for ``/predict``.

    Two ways to call it:
      1. Send ``messages`` (OpenAI-style chat list) for full control
         of the conversation/system prompt.
      2. Send ``prompt`` (and optional ``system``) for a one-shot
         text generation. We wrap it as ``[{system}, {user}]``
         internally.

    ``image_b64`` is accepted for forward-compat with Phase 2; in
    Phase 1 (no mmproj) it's silently ignored and the response signals
    ``vision_disabled``.
    """

    prompt: str | None = None
    system: str | None = None
    messages: list[ChatTurn] | None = None
    image_b64: str | None = None
    image_mime: str = "image/jpeg"
    max_tokens: int = Field(default=512, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    json_mode: bool = False  # If True, set response_format=json_object.


class PredictOut(BaseModel):
    output: str
    finish_reason: str | None = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    elapsed_ms: int = 0
    vision_used: bool = False
    vision_disabled: bool = False


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "dressapp-eyes",
        "phase": "1",
        "model": os.path.basename(MODEL_PATH),
        "vision_enabled": getattr(app.state, "vision_enabled", False),
        "endpoints": ["GET /", "GET /healthz", "POST /predict"],
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    if not getattr(app.state, "llm", None):
        # Lifespan still loading — surface a 503 so HF marks the Space
        # "starting" instead of "running".
        raise HTTPException(status_code=503, detail="model loading")
    return {
        "status": "ok",
        "model": os.path.basename(MODEL_PATH),
        "vision_enabled": app.state.vision_enabled,
        "uptime_s": int(time.time() - app.state.loaded_at),
    }


def _build_messages(req: PredictIn) -> list[dict[str, Any]]:
    """Normalise the request into an OpenAI-shaped messages list."""
    if req.messages:
        msgs: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in req.messages
        ]
    else:
        if not req.prompt:
            raise HTTPException(
                status_code=400,
                detail="send either 'messages' or 'prompt'",
            )
        msgs = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        msgs.append({"role": "user", "content": req.prompt})

    # Phase 2 vision attach: when mmproj is loaded AND the caller
    # sent an image, splice it into the LAST user turn as a content-
    # list per the LLaVA chat-format spec.
    if app.state.vision_enabled and req.image_b64:
        target_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "user":
                target_idx = i
                break
        if target_idx is None:
            msgs.append({"role": "user", "content": []})
            target_idx = len(msgs) - 1

        existing = msgs[target_idx]["content"]
        text_blob = existing if isinstance(existing, str) else ""
        data_url = f"data:{req.image_mime};base64,{req.image_b64}"
        msgs[target_idx]["content"] = [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": text_blob},
        ]
    return msgs


@app.post("/predict", response_model=PredictOut)
async def predict(req: PredictIn) -> PredictOut:
    """Single-turn or multi-turn completion against the fine-tuned model.

    Concurrency: llama.cpp keeps a single KV cache per context, so we
    serialise calls behind ``app.state.lock``. With CPU Basic giving
    us only 2 vCPUs this is also the right policy for throughput —
    splitting threads across two concurrent requests would actually
    be slower than serving them sequentially.
    """
    llm = app.state.llm
    if llm is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    msgs = _build_messages(req)

    kwargs: dict[str, Any] = {
        "messages": msgs,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
    }
    if req.json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    t0 = time.time()
    async with app.state.lock:
        # llama-cpp-python is sync; offload to a thread to keep the
        # event loop responsive (healthchecks etc.).
        try:
            res = await asyncio.to_thread(
                llm.create_chat_completion, **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("inference failure")
            raise HTTPException(
                status_code=500, detail=f"inference error: {exc}",
            ) from exc

    elapsed_ms = int((time.time() - t0) * 1000)
    choice = (res.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = res.get("usage") or {}
    return PredictOut(
        output=str(msg.get("content") or ""),
        finish_reason=choice.get("finish_reason"),
        tokens_prompt=int(usage.get("prompt_tokens") or 0),
        tokens_completion=int(usage.get("completion_tokens") or 0),
        elapsed_ms=elapsed_ms,
        vision_used=bool(app.state.vision_enabled and req.image_b64),
        vision_disabled=bool(req.image_b64 and not app.state.vision_enabled),
    )
