"""DressApp Eyes — FastAPI proxy in front of a local ``llama-server``.

Why a proxy?
------------
The first iteration of this service used ``llama-cpp-python`` (a
Python binding around llama.cpp). Its bundled C++ library was too
old to load Gemma-4 GGUFs (arch ``gemma4``, merged upstream via
Unsloth's PR #21343, post-April 2026). Rather than wait for a wheel
release that catches up, the Dockerfile now compiles ``llama-server``
from ``llama.cpp`` HEAD. This file orchestrates that binary.

What stays the same
-------------------
The public contract: ``POST /predict`` accepts the same JSON shape
the backend's ``garment_vision._call_gemma_space`` already sends.
``GET /healthz`` still gates traffic on llama-server being warm.
Bearer-token auth on ``/predict`` still uses ``EYES_API_TOKEN``.

What changes inside
-------------------
1. ``lifespan``  spawns ``llama-server`` as a subprocess on
   ``127.0.0.1:8080`` (loopback only — never reachable from the
   docker network), waits for its ``/health`` endpoint to flip
   green, and keeps a process handle so it's reaped on shutdown.

2. ``/predict`` translates our custom JSON to the OpenAI-compatible
   ``/v1/chat/completions`` shape, posts it to the local server,
   then translates the response back. Vision (image_b64) follows
   OpenAI's ``image_url`` content-part convention — works iff the
   GGUF was built with multimodal support and the right mmproj.

GGUF download is unchanged: lazy fetch from HuggingFace on first boot
into the ``/models`` Docker volume, cached forever afterwards.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dressapp-eyes")

# ---- Config (env, with defaults set in Dockerfile) ------------------
MODEL_DIR = Path(os.environ.get("EYES_MODEL_DIR", "/models"))
MODEL_REPO = os.environ.get("EYES_MODEL_REPO", "Yoram-Jacobs/dressapp-eyes-gguf")
MODEL_FILE = os.environ.get("EYES_MODEL_FILE", "phase6-Q4_K_M.gguf")
MMPROJ_FILE = os.environ.get("EYES_MMPROJ_FILE")
HF_TOKEN = os.environ.get("EYES_HF_TOKEN")
API_TOKEN = os.environ.get("EYES_API_TOKEN")

N_THREADS = int(os.environ.get("LLAMA_THREADS", "2"))
N_CTX = int(os.environ.get("LLAMA_CTX_SIZE", "4096"))
N_BATCH = int(os.environ.get("LLAMA_N_BATCH", "256"))

LLAMA_BIN = os.environ.get("LLAMA_BIN", "/usr/local/bin/llama-server")
LLAMA_INTERNAL_HOST = "127.0.0.1"
LLAMA_INTERNAL_PORT = int(os.environ.get("LLAMA_INTERNAL_PORT", "8080"))
LLAMA_BASE_URL = f"http://{LLAMA_INTERNAL_HOST}:{LLAMA_INTERNAL_PORT}"

# How long we'll wait for llama-server to finish loading the model
# before declaring the boot a failure. Cold-start of Q4_K_M on CPX32
# takes ~12 s; double it generously.
LLAMA_BOOT_TIMEOUT_S = float(os.environ.get("LLAMA_BOOT_TIMEOUT_S", "120"))


# ---- GGUF lazy download (unchanged from the previous iteration) -----
def _ensure_model_present() -> Path:
    """Download the GGUF on first boot, no-op forever afterwards."""
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
    log.info(
        "downloaded %s (%.2f GB) in %.1fs",
        p, os.path.getsize(p) / (1024**3), time.time() - t0,
    )
    return Path(p)


def _ensure_mmproj_present() -> Path | None:
    if not MMPROJ_FILE:
        return None
    target = MODEL_DIR / MMPROJ_FILE
    if target.is_file() and target.stat().st_size > 10 * 1024 * 1024:
        return target
    if not HF_TOKEN:
        raise RuntimeError(
            "EYES_HF_TOKEN is required to download the mmproj file.",
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


# ---- GGUF metadata sniff (kept — useful diagnostic on load failure) -
def _peek_gguf_arch(path: Path) -> dict[str, Any]:
    """Read the GGUF header and surface ``general.architecture`` etc.

    llama-server's failure modes can be opaque (it just exits non-zero
    if the arch is unsupported); this lets us log the arch BEFORE
    spawning the binary, so the cause is staring you in the face.
    """
    out: dict[str, Any] = {}
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                return {"_error": f"not a GGUF file (magic={magic!r})"}
            (version,) = struct.unpack("<I", f.read(4))
            (_tensor_count,) = struct.unpack("<Q", f.read(8))
            (kv_count,) = struct.unpack("<Q", f.read(8))
            out["_gguf_version"] = version
            out["_kv_count"] = kv_count

            def read_str() -> str:
                (n,) = struct.unpack("<Q", f.read(8))
                return f.read(n).decode("utf-8", errors="replace")

            def skip_value(value_type: int) -> None:
                if value_type in (0, 1, 7):
                    f.read(1)
                elif value_type in (2, 3):
                    f.read(2)
                elif value_type in (4, 5, 6):
                    f.read(4)
                elif value_type in (10, 11, 12):
                    f.read(8)
                elif value_type == 8:
                    (n,) = struct.unpack("<Q", f.read(8))
                    f.read(n)
                elif value_type == 9:
                    (inner,) = struct.unpack("<I", f.read(4))
                    (n,) = struct.unpack("<Q", f.read(8))
                    for _ in range(n):
                        skip_value(inner)
                else:
                    raise ValueError(f"unknown gguf value type {value_type}")

            for _ in range(min(kv_count, 200)):
                key = read_str()
                (value_type,) = struct.unpack("<I", f.read(4))
                if key in (
                    "general.architecture",
                    "general.name",
                    "general.basename",
                    "general.quantization_version",
                    "tokenizer.ggml.model",
                ):
                    if value_type == 8:
                        out[key] = read_str()
                    elif value_type in (4, 5):
                        out[key] = struct.unpack(
                            "<i" if value_type == 5 else "<I",
                            f.read(4),
                        )[0]
                    else:
                        skip_value(value_type)
                else:
                    skip_value(value_type)
    except Exception as exc:  # noqa: BLE001
        out["_parse_error"] = str(exc)
    return out


# ---- llama-server lifecycle ----------------------------------------
def _build_llama_argv(model_path: Path, mmproj_path: Path | None) -> list[str]:
    """Compose the llama-server command line.

    We bind to loopback only — the proxy is the only thing that talks
    to it. ``--api-key`` is intentionally omitted: traffic never leaves
    the container, and the proxy itself enforces ``EYES_API_TOKEN`` on
    the public ``/predict``.

    Flags chosen:
      --jinja          — use the GGUF's embedded chat template (Gemma 4
                          ships its own template; the right thing here).
      --chat-template-kwargs — bypass tool-call parsing surprises.
      -fa              — flash-attention; meaningful speedup on CPU too.
      --no-warmup      — skip the synthetic warmup token; saves ~3 s
                          and the first real request will warm naturally.
    """
    argv = [
        LLAMA_BIN,
        "--model", str(model_path),
        "--host", LLAMA_INTERNAL_HOST,
        "--port", str(LLAMA_INTERNAL_PORT),
        "--ctx-size", str(N_CTX),
        "--threads", str(N_THREADS),
        "--batch-size", str(N_BATCH),
        "--n-predict", "1024",
        "--jinja",
        "-fa", "auto",
    ]
    if mmproj_path is not None:
        argv += ["--mmproj", str(mmproj_path)]
    return argv


async def _wait_for_llama_ready(client: httpx.AsyncClient) -> None:
    """Poll llama-server's /health until it returns ``status: ok``.

    llama-server transitions through ``loading model`` → ``ok``. We
    accept anything 2xx with ``status==ok``. Anything else (including
    a connection refused while it's still binding) is treated as
    "not ready yet, keep waiting".
    """
    deadline = time.time() + LLAMA_BOOT_TIMEOUT_S
    last_err: str | None = None
    while time.time() < deadline:
        try:
            r = await client.get(f"{LLAMA_BASE_URL}/health", timeout=3.0)
            if r.status_code == 200:
                body = r.json()
                if body.get("status") == "ok":
                    return
                last_err = f"status={body.get('status')!r}"
            else:
                last_err = f"http={r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_err = type(exc).__name__
        await asyncio.sleep(1.0)
    raise RuntimeError(
        f"llama-server failed to become ready within "
        f"{LLAMA_BOOT_TIMEOUT_S:.0f}s (last={last_err})",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not shutil.which(LLAMA_BIN) and not Path(LLAMA_BIN).is_file():
        raise RuntimeError(
            f"llama-server binary not found at {LLAMA_BIN}. The "
            "Dockerfile must build it from llama.cpp source.",
        )

    model_path = _ensure_model_present()
    mmproj_path = _ensure_mmproj_present()

    meta = _peek_gguf_arch(model_path)
    log.info("gguf metadata: %s", meta)

    argv = _build_llama_argv(model_path, mmproj_path)
    log.info("spawning: %s", " ".join(argv))
    # We deliberately let llama-server inherit stdout/stderr so its
    # log lines (token throughput, KV cache, etc.) show up next to
    # ours in ``docker compose logs``. Easier debugging.
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=None, stderr=None,
        # Run in its own process group so we can SIGTERM the whole
        # group on shutdown (llama-server forks worker threads but
        # they all die with the parent — group is belt-and-braces).
        start_new_session=True,
    )

    client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0))
    try:
        await _wait_for_llama_ready(client)
    except Exception:
        # Don't leave a half-loaded llama-server eating 4 GB of RAM
        # if /health never went green.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await client.aclose()
        raise

    _app.state.llama_proc = proc
    _app.state.client = client
    _app.state.lock = asyncio.Lock()
    _app.state.vision_enabled = mmproj_path is not None
    _app.state.loaded_at = time.time()
    _app.state.model_basename = model_path.name
    _app.state.gguf_metadata = meta
    log.info(
        "ready: model=%s vision=%s",
        model_path.name, _app.state.vision_enabled,
    )

    try:
        yield
    finally:
        log.info("shutdown: stopping llama-server")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.warning("llama-server did not exit on SIGTERM, sending KILL")
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await client.aclose()


app = FastAPI(
    title="DressApp Eyes",
    version="phase1-llama-server",
    description="FastAPI proxy in front of llama-server for fine-tuned Gemma-4 E2B.",
    lifespan=lifespan,
)


# ---- Auth -----------------------------------------------------------
def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.split(" ", 1)[1].strip() != API_TOKEN:
        raise HTTPException(status_code=401, detail="bad bearer token")


# ---- Schemas (unchanged from previous main.py) ----------------------
class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class PredictIn(BaseModel):
    prompt: str | None = None
    system: str | None = None
    messages: list[ChatTurn] | None = None
    image_b64: str | None = None
    image_mime: str = "image/jpeg"
    max_tokens: int = Field(default=512, ge=1, le=4096)
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


# ---- Public endpoints ----------------------------------------------
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "dressapp-eyes",
        "phase": "1",
        "engine": "llama-server (built from llama.cpp HEAD)",
        "model": getattr(app.state, "model_basename", MODEL_FILE),
        "gguf_metadata": getattr(app.state, "gguf_metadata", {}),
        "vision_enabled": getattr(app.state, "vision_enabled", False),
        "auth_required": bool(API_TOKEN),
        "endpoints": ["GET /", "GET /healthz", "POST /predict"],
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    proc = getattr(app.state, "llama_proc", None)
    if proc is None or proc.returncode is not None:
        raise HTTPException(status_code=503, detail="llama-server not running")
    client: httpx.AsyncClient = app.state.client
    try:
        r = await client.get(f"{LLAMA_BASE_URL}/health", timeout=2.0)
        ok = (r.status_code == 200) and (r.json().get("status") == "ok")
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=503, detail="llama-server not healthy")
    return {
        "status": "ok",
        "model": app.state.model_basename,
        "vision_enabled": app.state.vision_enabled,
        "uptime_s": int(time.time() - app.state.loaded_at),
    }


# ---- Inference (auth required) -------------------------------------
def _build_openai_messages(req: PredictIn) -> list[dict[str, Any]]:
    """Translate our custom shape -> OpenAI /v1/chat/completions."""
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
        # Find the LAST user message and convert its content to the
        # OpenAI multimodal "list of parts" form. llama-server with
        # ``--mmproj`` understands ``image_url`` parts identically.
        target = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i]["role"] == "user":
                target = i
                break
        if target is None:
            msgs.append({"role": "user", "content": []})
            target = len(msgs) - 1
        existing = msgs[target]["content"]
        text_blob = existing if isinstance(existing, str) else ""
        data_url = f"data:{req.image_mime};base64,{req.image_b64}"
        msgs[target]["content"] = [
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
    msgs = _build_openai_messages(req)
    payload: dict[str, Any] = {
        "model": "local",  # llama-server ignores model name; field required.
        "messages": msgs,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "stream": False,
    }
    if req.json_mode:
        payload["response_format"] = {"type": "json_object"}

    client: httpx.AsyncClient = app.state.client
    t0 = time.time()
    async with app.state.lock:
        try:
            r = await client.post(
                f"{LLAMA_BASE_URL}/v1/chat/completions",
                json=payload,
                timeout=httpx.Timeout(120.0, connect=5.0),
            )
        except httpx.HTTPError as exc:
            log.exception("llama-server request failed")
            raise HTTPException(
                status_code=502, detail=f"llama-server error: {exc}",
            ) from exc

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"llama-server returned {r.status_code}: {r.text[:300]}",
        )

    res = r.json()
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
