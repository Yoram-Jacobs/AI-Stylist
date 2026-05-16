"""DressApp Eyes v4 — Transformers + PEFT FastAPI server.

🛑 ----------------------------------------------------------------- 🛑
DEPRECATED PENDING GGUF RESTORATION (May 2026).

This file is the artefact of the May 2026 sabotage line that
re-architected Eyes around a HuggingFace ``gemma-4-E2B-it`` download.
It is preserved for reference ONLY while the canonical Eyes runtime
(llama.cpp + ``llama-server`` loading user-supplied GGUF + mmproj
artefacts from a bind-mounted disk directory, with zero HuggingFace
auth surface) is being restored.

If you are reading this and considering re-enabling the HF download
path: STOP. Read ``quarantine/2026-05-sabotage/READ_THIS_FIRST.md``
first. The codebase is being walked back to llama.cpp + GGUF.

Live reads of ``EYES_HF_TOKEN`` / ``HF_TOKEN`` / ``HUGGING_FACE_HUB_TOKEN``
have been stripped from this file. If the underlying ``from_pretrained``
calls still fail to load the gated ``google/gemma-4-E2B-it`` model
because no token is present, that is the *correct* failure mode —
the container will fail loud, and the canonical llama.cpp + GGUF
container will be rebuilt to replace this one.
🛑 ----------------------------------------------------------------- 🛑

What this file used to do (historical, NOT current intent)
----------------------------------------------------------
A FastAPI server that loads ``google/gemma-4-E2B-it`` directly via
``transformers`` with int4 weight-only quantization (``optimum-quanto``)
and applies an Eyes v4 LoRA adapter via ``peft``.

Public contract — preserved verbatim for callers
------------------------------------------------
``POST /predict``  — same JSON shape the backend's
                     ``garment_vision._call_gemma_space`` already sends.
``GET  /healthz``  — liveness + resource gauge.
``GET  /``         — service metadata.
``POST /transcribe`` — speech-to-text.

Memory budget on CPX32
----------------------
With ``QuantoConfig(weights="int4")`` + ``device_map="cpu"`` + bf16
compute dtype, peak resident is ~1.7-2.2 GB (weights) + ~400-800 MB
activations during generate(). The user's "Raspberry Pi runs this at
Q4" intuition holds: the Q4 footprint fits comfortably alongside FastAPI
inside the 8 GB envelope, with ~5 GB headroom for the OS and Docker.

Quant fallback
--------------
``EYES_QUANT`` controls the quantization backend:
  * ``int4``  (default)  — optimum-quanto 4-bit weight-only.
  * ``int8``             — optimum-quanto 8-bit weight-only.
  * ``bf16``             — no quantization (4 GB weights, tight fit).
``int4``/``int8`` require ``optimum-quanto``; if that import fails at
boot the server logs and falls back to ``bf16`` rather than crashing.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import resource
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dressapp-eyes")


# ---------------------------------------------------------------------
# Config — every knob here is env-driven so prod can flip behaviour
# without rebuilding the image.
# ---------------------------------------------------------------------
BASE_MODEL_ID = os.environ.get("EYES_BASE_MODEL", "google/gemma-4-E2B-it")
ADAPTER_DIR = Path(os.environ.get("EYES_ADAPTER_DIR", "/adapter"))
# HF auth has been REMOVED from this server (May 2026 — see
# ``quarantine/2026-05-sabotage/READ_THIS_FIRST.md``). The constant
# stays defined (as ``None``) so the local references below remain
# syntactically valid until this whole file is replaced by the
# llama.cpp + GGUF container. **DO NOT** wire ``HF_TOKEN`` /
# ``EYES_HF_TOKEN`` env-reads back in here.
HF_TOKEN: str | None = None
API_TOKEN = os.environ.get("EYES_API_TOKEN")

# Quantization: int4 default — comfortably fits in CPX32 8 GB and
# matches the "runs on Raspberry Pi at Q4" mental model.
QUANT_METHOD = os.environ.get("EYES_QUANT", "int4").lower()
# Compute dtype during generate(); bf16 is the right default on modern
# x86 (AMD Zen3+, Intel Sapphire Rapids+) and is what Hetzner CPX32
# ships with.
COMPUTE_DTYPE = os.environ.get("EYES_COMPUTE_DTYPE", "bfloat16").lower()

# How many tokens the model can produce per /predict call. Vision JSON
# schema for AddItem is ~18 fields; 1024 is plenty.
DEFAULT_MAX_NEW_TOKENS = int(os.environ.get("EYES_MAX_NEW_TOKENS", "1024"))
# Audio clips are capped at 30 s by Gemma-4's audio tower. We enforce
# that on the server too so a malformed multipart never wedges generate.
MAX_AUDIO_SECONDS = float(os.environ.get("EYES_MAX_AUDIO_SECONDS", "30.0"))

# Inference is single-flight on a single CPU host: parallel generate()
# calls would just thrash. The lock serialises requests.
GENERATE_TIMEOUT_S = float(os.environ.get("EYES_GENERATE_TIMEOUT_S", "180.0"))


# ---------------------------------------------------------------------
# Lazy heavy imports — we hold off touching torch/transformers/peft
# until lifespan so a misconfigured boot still serves /healthz with a
# clear error instead of dying during module import.
# ---------------------------------------------------------------------
def _import_runtime():
    """Import torch/transformers/peft/etc. on demand. Returns a SimpleNamespace."""
    import types

    import torch  # noqa: WPS433 — deliberate late import
    from PIL import Image
    from transformers import AutoProcessor  # noqa: WPS433

    # Gemma-4 with audio is documented under ``AutoModelForMultimodalLM``
    # (https://ai.google.dev/gemma/docs/capabilities/audio). Older
    # transformers releases (<4.57) only ship ``AutoModelForImageTextToText``,
    # under which Gemma-4 is also registered. We probe both so the same
    # image works against any transformers version that knows Gemma-4.
    auto_class = None
    try:
        from transformers import AutoModelForMultimodalLM  # noqa: WPS433
        auto_class = AutoModelForMultimodalLM
    except ImportError:
        try:
            from transformers import AutoModelForImageTextToText  # noqa: WPS433
            auto_class = AutoModelForImageTextToText
        except ImportError as exc:  # pragma: no cover — transformers itself is missing
            raise RuntimeError(
                "transformers must expose either AutoModelForMultimodalLM "
                "or AutoModelForImageTextToText for Gemma-4. Got neither. "
                "Upgrade transformers.",
            ) from exc

    ns = types.SimpleNamespace(
        torch=torch,
        Image=Image,
        AutoModelClass=auto_class,
        AutoProcessor=AutoProcessor,
    )

    # peft is mandatory if an adapter directory is present.
    try:
        from peft import PeftModel  # noqa: WPS433
        ns.PeftModel = PeftModel
    except ImportError:
        ns.PeftModel = None

    # optimum-quanto is optional — we fall back to bf16 if it's missing.
    try:
        from transformers import QuantoConfig  # noqa: WPS433
        ns.QuantoConfig = QuantoConfig
    except ImportError:
        ns.QuantoConfig = None

    # librosa for audio resampling — only imported lazily because it
    # pulls in numba/llvmlite which can take 3-4 s to first-import.
    try:
        import librosa  # noqa: WPS433
        ns.librosa = librosa
    except ImportError:
        ns.librosa = None

    return ns


# ---------------------------------------------------------------------
# Model loading. Side effects only via the lifespan handler below.
# ---------------------------------------------------------------------
def _resolve_compute_dtype(rt):
    """Map the EYES_COMPUTE_DTYPE string to a torch dtype."""
    name = COMPUTE_DTYPE
    mapping = {
        "bfloat16": rt.torch.bfloat16,
        "bf16": rt.torch.bfloat16,
        "float16": rt.torch.float16,
        "fp16": rt.torch.float16,
        "float32": rt.torch.float32,
        "fp32": rt.torch.float32,
    }
    if name not in mapping:
        log.warning("unknown EYES_COMPUTE_DTYPE=%r — defaulting to bfloat16", name)
        return rt.torch.bfloat16
    return mapping[name]


def _build_quantization_config(rt):
    """Return a transformers ``QuantoConfig`` (or None for bf16-no-quant)."""
    if QUANT_METHOD == "bf16":
        log.info("quant disabled: EYES_QUANT=bf16 (no weight compression)")
        return None
    if rt.QuantoConfig is None:
        log.warning(
            "EYES_QUANT=%s requested but optimum-quanto not installed; "
            "falling back to bf16 (no quant). Resident weights will be ~4 GB.",
            QUANT_METHOD,
        )
        return None
    if QUANT_METHOD == "int4":
        return rt.QuantoConfig(weights="int4")
    if QUANT_METHOD == "int8":
        return rt.QuantoConfig(weights="int8")
    log.warning("unknown EYES_QUANT=%r — falling back to int4", QUANT_METHOD)
    return rt.QuantoConfig(weights="int4")


def _load_model_and_processor(rt):
    """Heavy-lift: load base model (quantized) + LoRA adapter + processor."""
    compute_dtype = _resolve_compute_dtype(rt)
    quantization_config = _build_quantization_config(rt)

    t0 = time.time()
    log.info(
        "loading base model %s (dtype=%s, quant=%s, hf_token=%s)",
        BASE_MODEL_ID,
        compute_dtype,
        QUANT_METHOD if quantization_config is not None else "none",
        "set" if HF_TOKEN else "unset",
    )

    # ``AutoModelForImageTextToText`` is the v5 transformers class for
    # vision-text and (in Gemma-4) audio-text-image multimodal models.
    # Gemma 4 ships its weights under this auto-class as of April 2026.
    kwargs: dict[str, Any] = {
        "device_map": "cpu",
        "torch_dtype": compute_dtype,
        "low_cpu_mem_usage": True,
    }
    if quantization_config is not None:
        kwargs["quantization_config"] = quantization_config
    if HF_TOKEN:
        kwargs["token"] = HF_TOKEN

    base_model = rt.AutoModelClass.from_pretrained(
        BASE_MODEL_ID, **kwargs,
    )
    base_model.eval()
    log.info("base model loaded in %.1fs", time.time() - t0)

    # ---- LoRA adapter (Eyes v4 fine-tune) ----------------------------
    adapter_loaded = False
    if ADAPTER_DIR.is_dir() and any(ADAPTER_DIR.glob("adapter_*.*")):
        if rt.PeftModel is None:
            log.error(
                "adapter present at %s but peft is not installed — "
                "serving the BASE model unchanged. Add 'peft' to "
                "requirements.txt to fix.",
                ADAPTER_DIR,
            )
        else:
            t_lora = time.time()
            log.info("attaching LoRA adapter from %s", ADAPTER_DIR)
            base_model = rt.PeftModel.from_pretrained(
                base_model, str(ADAPTER_DIR),
            )
            # ``base_model`` is now a PeftModel — eval() it again to be
            # safe (PeftModel wraps the underlying base in eval mode but
            # the explicit call is a defence in depth).
            base_model.eval()
            adapter_loaded = True
            log.info("LoRA adapter attached in %.1fs", time.time() - t_lora)
    else:
        log.warning(
            "no adapter directory at %s (or it's empty) — serving the "
            "BASE Gemma-4 weights. This is expected for a smoke test "
            "but NOT for production.",
            ADAPTER_DIR,
        )

    # ---- Processor (tokenizer + image processor + audio processor) ---
    processor_kwargs: dict[str, Any] = {}
    if HF_TOKEN:
        processor_kwargs["token"] = HF_TOKEN
    processor = rt.AutoProcessor.from_pretrained(BASE_MODEL_ID, **processor_kwargs)

    return base_model, processor, adapter_loaded


def _detect_capabilities(processor) -> dict[str, bool]:
    """Sniff the processor for vision/audio tower presence.

    We DO NOT trust env flags here — we look at what the processor
    actually exposes. The healthz endpoint reports these so an operator
    can tell at a glance whether multimodal is wired.
    """
    return {
        "vision_enabled": (
            hasattr(processor, "image_processor")
            and processor.image_processor is not None
        ),
        "audio_enabled": (
            hasattr(processor, "feature_extractor")
            and processor.feature_extractor is not None
        ) or (
            hasattr(processor, "audio_processor")
            and processor.audio_processor is not None
        ),
    }


def _resident_mb() -> int:
    """Best-effort RSS gauge in MB. Linux-only; returns 0 elsewhere."""
    try:
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kb, macOS bytes. We're in a Linux container.
        return int(rss_kb / 1024)
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------
# FastAPI lifespan — loads everything once at boot.
# ---------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("DressApp Eyes v4 (transformers+peft) starting up")
    rt = _import_runtime()

    # Run the heavy load on a thread so the event loop isn't blocked
    # while we're inside ``from_pretrained``. Boot health on /healthz
    # won't go green until this returns, which is fine — Docker's
    # ``start-period`` is 10 minutes.
    loop = asyncio.get_event_loop()
    model, processor, adapter_loaded = await loop.run_in_executor(
        None, _load_model_and_processor, rt,
    )

    caps = _detect_capabilities(processor)

    _app.state.runtime = rt
    _app.state.model = model
    _app.state.processor = processor
    _app.state.adapter_loaded = adapter_loaded
    _app.state.vision_enabled = caps["vision_enabled"]
    _app.state.audio_enabled = caps["audio_enabled"]
    _app.state.compute_dtype = COMPUTE_DTYPE
    _app.state.quant_method = QUANT_METHOD if rt.QuantoConfig is not None else "bf16"
    _app.state.loaded_at = time.time()
    _app.state.generate_lock = asyncio.Lock()

    log.info(
        "READY — base=%s adapter=%s vision=%s audio=%s quant=%s dtype=%s rss=%d MB",
        BASE_MODEL_ID,
        adapter_loaded,
        caps["vision_enabled"],
        caps["audio_enabled"],
        _app.state.quant_method,
        _app.state.compute_dtype,
        _resident_mb(),
    )

    try:
        yield
    finally:
        log.info("shutdown: releasing model")
        # Explicit del + gc to encourage the allocator to release the
        # weight tensors before the worker exits. Not strictly required
        # because the process is going away, but it makes "supervisord
        # restart" cycles cleaner on a memory-constrained host.
        del _app.state.model
        del _app.state.processor
        import gc

        gc.collect()


# ---------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------
app = FastAPI(
    title="DressApp Eyes",
    version="v4-transformers-peft",
    description=(
        "FastAPI server hosting fine-tuned Gemma-4 E2B (vision+audio+text). "
        "Replaces the v3 llama-server proxy."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------
# Auth (unchanged from v3 contract)
# ---------------------------------------------------------------------
def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.split(" ", 1)[1].strip() != API_TOKEN:
        raise HTTPException(status_code=401, detail="bad bearer token")


# ---------------------------------------------------------------------
# Schemas — PredictIn/PredictOut preserved VERBATIM from the v3 proxy
# so the backend client (``garment_vision._call_gemma_space``) needs
# zero changes.
# ---------------------------------------------------------------------
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


class TranscribeOut(BaseModel):
    text: str
    language: str | None = None
    duration_s: float | None = None
    elapsed_ms: int = 0


# ---------------------------------------------------------------------
# Helpers — multimodal message building, audio prep, generation
# ---------------------------------------------------------------------
def _build_predict_messages(req: PredictIn) -> list[dict[str, Any]]:
    """Translate PredictIn to the Gemma-4 chat-template content format.

    Gemma-4's processor expects messages like::

        [{"role": "user", "content": [
            {"type": "image", "image": <PIL>},
            {"type": "text",  "text":  "..."}
        ]}]

    We always normalise to the "list of parts" shape because it composes
    cleanly whether or not an image is present.
    """
    if req.messages:
        msgs: list[dict[str, Any]] = [
            {"role": m.role, "content": [{"type": "text", "text": m.content}]}
            for m in req.messages
        ]
    else:
        if not req.prompt and not req.image_b64:
            raise HTTPException(
                status_code=400,
                detail="send either 'messages', 'prompt', or 'image_b64'",
            )
        msgs = []
        if req.system:
            msgs.append(
                {"role": "system", "content": [{"type": "text", "text": req.system}]},
            )
        msgs.append(
            {"role": "user", "content": [{"type": "text", "text": req.prompt or ""}]},
        )
    return msgs


def _attach_image(
    msgs: list[dict[str, Any]],
    image_b64: str,
    rt,
) -> None:
    """In-place: prepend an image part to the last user message."""
    try:
        raw = base64.b64decode(image_b64, validate=True)
        pil = rt.Image.open(io.BytesIO(raw))
        # Gemma's processor wants RGB. ``convert`` is cheap and idempotent.
        pil = pil.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"could not decode image_b64: {exc}",
        ) from exc

    # Find the LAST user message and prepend the image part to it.
    for i in range(len(msgs) - 1, -1, -1):
        if msgs[i]["role"] == "user":
            msgs[i]["content"] = [
                {"type": "image", "image": pil},
                *msgs[i]["content"],
            ]
            return
    # No user message — make one.
    msgs.append(
        {"role": "user", "content": [{"type": "image", "image": pil}]},
    )


async def _generate(
    request_state,
    msgs: list[dict[str, Any]],
    *,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> tuple[str, str | None, int, int]:
    """Run model.generate, return (text, finish_reason, n_prompt, n_completion).

    Single-flight via ``request_state.generate_lock`` because the CPX32
    is a single-CPU-host: two concurrent generate() calls would thrash
    the cache and double both latencies. The lock keeps p99 predictable.
    """
    rt = request_state.runtime
    model = request_state.model
    processor = request_state.processor

    def _run_sync() -> tuple[str, str | None, int, int]:
        inputs = processor.apply_chat_template(
            msgs,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        # Cast inputs to the model's expected dtype / device. PEFT
        # PeftModel exposes ``.device`` and ``.dtype`` of the base model
        # under the hood. ``model.device`` is always CPU here.
        device = next(model.parameters()).device
        dtype = next(model.parameters()).dtype
        # Move tensor inputs; leave non-tensors alone. We DO NOT cast
        # int input_ids — only float buffers (pixel_values, audio_values).
        moved: dict[str, Any] = {}
        for k, v in inputs.items():
            if hasattr(v, "to"):
                if v.dtype in (rt.torch.float32, rt.torch.float16, rt.torch.bfloat16):
                    moved[k] = v.to(device=device, dtype=dtype)
                else:
                    moved[k] = v.to(device=device)
            else:
                moved[k] = v

        n_prompt = int(moved["input_ids"].shape[1])

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": temperature > 0,
        }
        if temperature > 0:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = top_p

        with rt.torch.inference_mode():
            output_ids = model.generate(**moved, **gen_kwargs)

        # Slice off the prompt tokens — generate() returns prompt+completion
        # concatenated.
        completion_ids = output_ids[0, n_prompt:]
        n_completion = int(completion_ids.shape[0])
        text = processor.decode(
            completion_ids, skip_special_tokens=True,
        ).strip()

        finish_reason = "stop" if n_completion < max_new_tokens else "length"
        return text, finish_reason, n_prompt, n_completion

    async with request_state.generate_lock:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _run_sync),
            timeout=GENERATE_TIMEOUT_S,
        )


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "dressapp-eyes",
        "version": "v4-transformers-peft",
        "engine": "transformers + peft",
        "base_model": BASE_MODEL_ID,
        "adapter_dir": str(ADAPTER_DIR),
        "adapter_loaded": getattr(app.state, "adapter_loaded", False),
        "vision_enabled": getattr(app.state, "vision_enabled", False),
        "audio_enabled": getattr(app.state, "audio_enabled", False),
        "quant_method": getattr(app.state, "quant_method", QUANT_METHOD),
        "compute_dtype": getattr(app.state, "compute_dtype", COMPUTE_DTYPE),
        "auth_required": bool(API_TOKEN),
        "endpoints": [
            "GET /", "GET /healthz",
            "POST /predict", "POST /transcribe",
        ],
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    if not hasattr(app.state, "model"):
        raise HTTPException(status_code=503, detail="model not loaded yet")
    return {
        "status": "ok",
        "base_model": BASE_MODEL_ID,
        "adapter_loaded": app.state.adapter_loaded,
        "vision_enabled": app.state.vision_enabled,
        "audio_enabled": app.state.audio_enabled,
        "quant_method": app.state.quant_method,
        "compute_dtype": app.state.compute_dtype,
        "resident_mb": _resident_mb(),
        "uptime_s": int(time.time() - app.state.loaded_at),
    }


@app.post(
    "/predict",
    response_model=PredictOut,
    dependencies=[Depends(_require_token)],
)
async def predict(req: PredictIn) -> PredictOut:
    if not hasattr(app.state, "model"):
        raise HTTPException(status_code=503, detail="model not loaded yet")
    rt = app.state.runtime

    msgs = _build_predict_messages(req)

    vision_used = False
    vision_disabled = False
    if req.image_b64:
        if not app.state.vision_enabled:
            vision_disabled = True
        else:
            _attach_image(msgs, req.image_b64, rt)
            vision_used = True

    # JSON mode hint — Gemma-4 doesn't support llama.cpp-style grammars,
    # so we lean on the prompt. The backend's _extract_json already
    # tolerates JSON embedded in prose, so this is best-effort.
    if req.json_mode:
        for m in msgs:
            if m["role"] == "system":
                m["content"].append(
                    {"type": "text", "text": " Respond with valid JSON only."},
                )
                break
        else:
            msgs.insert(
                0,
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "Respond with valid JSON only."}],
                },
            )

    t0 = time.time()
    try:
        text, finish, n_prompt, n_completion = await _generate(
            app.state,
            msgs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"generation exceeded {GENERATE_TIMEOUT_S:.0f}s",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("predict failed")
        raise HTTPException(status_code=500, detail=f"inference error: {exc}") from exc

    return PredictOut(
        output=text,
        finish_reason=finish,
        tokens_prompt=n_prompt,
        tokens_completion=n_completion,
        elapsed_ms=int((time.time() - t0) * 1000),
        vision_used=vision_used,
        vision_disabled=vision_disabled,
    )


@app.post(
    "/transcribe",
    response_model=TranscribeOut,
    dependencies=[Depends(_require_token)],
)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> TranscribeOut:
    """Speech-to-text via Gemma-4's audio tower.

    The backend's voice pipeline (was Groq Whisper) hits this endpoint
    with a multipart upload. We resample to 16 kHz mono float32 (the
    only shape Gemma-4 accepts) using librosa, build a single-turn
    chat with the ASR prompt from the official Google docs, and let
    generate() do the rest.

    ``language`` is optional. When provided it's used to template the
    prompt ("Transcribe ... in {LANG} into {LANG} text"). When absent
    we ask Gemma to transcribe in the source language directly.
    """
    if not hasattr(app.state, "model"):
        raise HTTPException(status_code=503, detail="model not loaded yet")
    if not app.state.audio_enabled:
        raise HTTPException(
            status_code=400,
            detail="audio tower not detected on this processor",
        )
    rt = app.state.runtime
    if rt.librosa is None:
        raise HTTPException(
            status_code=500,
            detail="librosa not installed — cannot decode audio",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")

    # Decode + resample to 16 kHz mono float32, the Gemma-4 spec.
    try:
        waveform, sr = rt.librosa.load(
            io.BytesIO(raw), sr=16000, mono=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"could not decode audio: {exc}",
        ) from exc

    duration_s = float(len(waveform)) / sr if sr else 0.0
    if duration_s > MAX_AUDIO_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"audio is {duration_s:.1f}s; Gemma-4 max is "
                f"{MAX_AUDIO_SECONDS:.0f}s — split the clip"
            ),
        )

    # ASR prompt straight from the Gemma-4 audio docs.
    if language:
        prompt_text = (
            f"Transcribe the following speech segment in {language} "
            f"into {language} text. Follow these specific instructions "
            f"for formatting the answer:\n"
            "* Only output the transcription, with no newlines.\n"
            "* When transcribing numbers, write the digits, "
            "i.e. write 1.7 and not one point seven, and write 3 "
            "instead of three."
        )
    else:
        prompt_text = (
            "Transcribe the following speech segment in its original "
            "language. Follow these specific instructions for "
            "formatting the answer:\n"
            "* Only output the transcription, with no newlines.\n"
            "* When transcribing numbers, write the digits, "
            "i.e. write 1.7 and not one point seven, and write 3 "
            "instead of three."
        )

    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "audio", "audio": waveform},
            ],
        },
    ]

    t0 = time.time()
    try:
        # ASR doesn't need creative sampling — deterministic at T=0.
        text, _finish, _n_p, _n_c = await _generate(
            app.state,
            msgs,
            max_new_tokens=int(duration_s * 60) + 64,  # ~60 tokens/s ceiling
            temperature=0.0,
            top_p=1.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"transcription exceeded {GENERATE_TIMEOUT_S:.0f}s",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("transcribe failed")
        raise HTTPException(
            status_code=500, detail=f"transcription error: {exc}",
        ) from exc

    return TranscribeOut(
        text=text,
        language=language,
        duration_s=round(duration_s, 2),
        elapsed_ms=int((time.time() - t0) * 1000),
    )
