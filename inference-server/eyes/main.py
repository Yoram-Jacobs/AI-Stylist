"""DressApp Eyes — self-hosted Gemma-4 E2B inference service (Hetzner).

Drop-in replacement for the Qwen-VL leg of the closet pipeline. Hits
the same JSON contract our backend's ``garment_vision._call_gemma_space``
already expects:

    POST /predict
    Authorization: Bearer <EYES_API_TOKEN>
    Content-Type:  application/json
    Body: {
        "prompt":     "...",          # OR
        "messages":   [...],          # OpenAI chat shape
        "system":     "...",          # optional
        "image_b64":  "...",          # ignored in Phase 1 (no mmproj)
        "image_mime": "image/jpeg",
        "max_tokens": 512,
        "temperature": 0.2,
        "json_mode":  false
    }
    -> { output, finish_reason, tokens_prompt, tokens_completion,
         elapsed_ms, vision_used, vision_disabled }

Lifecycle:
  1. Boot: lazy-download the fine-tuned GGUF from the private HF repo
     (or skip if it's already cached in the mounted volume) using
     ``EYES_HF_TOKEN``. Then load it into llama.cpp once.
  2. Health: ``GET /healthz`` returns 503 until the model is loaded,
     200 afterwards. Compose marks the service healthy only after
     200, so backend startup ordering stays correct.
  3. Auth: every endpoint except ``GET /`` and ``GET /healthz`` requires
     ``Authorization: Bearer <EYES_API_TOKEN>``. If ``EYES_API_TOKEN``
     is unset, auth is disabled (intended only for local debugging).
  4. Concurrency: llama.cpp keeps a single KV cache per context, so
     we serialise inference behind an asyncio.Lock. With 2 vCPUs that's
     also the right policy for throughput — splitting threads across
     concurrent requests would be slower than serving sequentially.

See ``inference-server/eyes/README.md`` for deploy instructions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dressapp-eyes")

# ---- Config (all from env, with sane defaults) -----------------------
MODEL_DIR = Path(os.environ.get("EYES_MODEL_DIR", "/models"))
MODEL_REPO = os.environ.get("EYES_MODEL_REPO", "Yoram-Jacobs/dressapp-eyes-gguf")
MODEL_FILE = os.environ.get("EYES_MODEL_FILE", "phase6-Q4_K_M.gguf")
MMPROJ_FILE = os.environ.get("EYES_MMPROJ_FILE")  # set in Phase 2
HF_TOKEN = os.environ.get("EYES_HF_TOKEN")

API_TOKEN = os.environ.get("EYES_API_TOKEN")  # bearer for backend->eyes

N_THREADS = int(os.environ.get("LLAMA_THREADS", "2"))
N_CTX = int(os.environ.get("LLAMA_CTX_SIZE", "4096"))
N_BATCH = int(os.environ.get("LLAMA_N_BATCH", "256"))


# ---- Lazy model download --------------------------------------------
def _ensure_model_present() -> Path:
    """Download the GGUF on first boot, then no-op forever.

    The container mounts a named docker volume at ``/models`` so
    repeated rebuilds, redeploys, and even ``docker compose down``
    won't trigger another 3.4 GB pull. Only an explicit
    ``docker volume rm dressapp_eyes-cache`` does.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / MODEL_FILE
    if target.is_file() and target.stat().st_size > 100 * 1024 * 1024:
        log.info(
            "model already cached: %s (%.2f GB)",
            target, target.stat().st_size / (1024**3),
        )
        return target

    if not HF_TOKEN:
        raise RuntimeError(
            "EYES_HF_TOKEN is not set; cannot download the private "
            f"model {MODEL_REPO}/{MODEL_FILE}."
        )

    log.info("downloading model: %s/%s", MODEL_REPO, MODEL_FILE)
    from huggingface_hub import hf_hub_download

    t0 = time.time()
    p = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILE,
        local_dir=str(MODEL_DIR),
        token=HF_TOKEN,
    )
    elapsed = time.time() - t0
    size = os.path.getsize(p) / (1024**3)
    log.info("downloaded %s (%.2f GB) in %.1fs", p, size, elapsed)
    return Path(p)


def _ensure_mmproj_present() -> Path | None:
    """Download the optional vision projector if EYES_MMPROJ_FILE is set."""
    if not MMPROJ_FILE:
        return None
    target = MODEL_DIR / MMPROJ_FILE
    if target.is_file() and target.stat().st_size > 10 * 1024 * 1024:
        return target
    if not HF_TOKEN:
        raise RuntimeError(
            "EYES_HF_TOKEN is required to download the mmproj file."
        )
    from huggingface_hub import hf_hub_download

    log.info("downloading mmproj: %s/%s", MODEL_REPO, MMPROJ_FILE)
    p = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MMPROJ_FILE,
        local_dir=str(MODEL_DIR),
        token=HF_TOKEN,
    )
    return Path(p)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from llama_cpp import Llama

    model_path = _ensure_model_present()
    mmproj_path = _ensure_mmproj_present()

    chat_handler = None
    vision_enabled = False
    if mmproj_path is not None:
        from llama_cpp.llama_chat_format import Llava15ChatHandler

        log.info("vision projector found: %s", mmproj_path)
        chat_handler = Llava15ChatHandler(clip_model_path=str(mmproj_path))
        vision_enabled = True

    log.info(
        "loading model: %s (threads=%d ctx=%d)",
        model_path, N_THREADS, N_CTX,
    )
    t0 = time.time()
    llm = Llama(
        model_path=str(model_path),
        n_ctx=N_CTX,
        n_threads=N_THREADS,
        n_batch=N_BATCH,
        chat_handler=chat_handler,
        chat_format="gemma" if chat_handler is None else None,
        # mmap is faster than read() on a single resident process; on
        # a 4 GB-RAM CX22 it also lets the kernel reclaim cold pages
        # under pressure instead of OOM-killing the whole container.
        use_mmap=True,
        use_mlock=False,
        verbose=False,
        logits_all=False,
    )
    _app.state.llm = llm
    _app.state.lock = asyncio.Lock()
    _app.state.vision_enabled = vision_enabled
    _app.state.loaded_at = time.time()
    _app.state.model_basename = model_path.name
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
    version="phase1-q4km-hetzner",
    description="Self-hosted fine-tuned Gemma-4 E2B for garment analysis.",
    lifespan=lifespan,
)


# ---- Auth -----------------------------------------------------------
def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return  # auth disabled (dev only)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.split(" ", 1)[1].strip() != API_TOKEN:
        raise HTTPException(status_code=401, detail="bad bearer token")


# ---- Schemas --------------------------------------------------------
class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class PredictIn(BaseModel):
    prompt: str | None = None
    system: str | None = None
    messages: list[ChatTurn] | None = None
    image_b64: str | None = None
    image_mime: str = "image/jpeg"
    max_tokens: int = Field(default=512, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    json_mode: bool = False


class PredictOut(BaseModel):
    output: str
    finish_reason: str | None = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    elapsed_ms: int = 0
    vision_used: bool = False
    vision_disabled: bool = False


# ---- Public endpoints (no auth) -------------------------------------
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "dressapp-eyes",
        "phase": "1",
        "model": getattr(app.state, "model_basename", MODEL_FILE),
        "vision_enabled": getattr(app.state, "vision_enabled", False),
        "auth_required": bool(API_TOKEN),
        "endpoints": ["GET /", "GET /healthz", "POST /predict"],
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    if not getattr(app.state, "llm", None):
        raise HTTPException(status_code=503, detail="model loading")
    return {
        "status": "ok",
        "model": app.state.model_basename,
        "vision_enabled": app.state.vision_enabled,
        "uptime_s": int(time.time() - app.state.loaded_at),
    }


# ---- Inference (auth required) --------------------------------------
def _build_messages(req: PredictIn) -> list[dict[str, Any]]:
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


@app.post(
    "/predict",
    response_model=PredictOut,
    dependencies=[Depends(_require_token)],
)
async def predict(req: PredictIn) -> PredictOut:
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
