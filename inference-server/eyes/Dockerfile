# DressApp Eyes v4 — Transformers + PEFT container (CPU-only).
#
# WHY THIS DROPS THE LLAMA.CPP BUILD STAGE
# =========================================
# The v3 Dockerfile compiled llama-server from llama.cpp HEAD to serve
# Gemma-4 GGUFs. Eyes v4 cannot use that pipeline because upstream
# llama.cpp does not yet support Gemma-4 multimodal LoRA → GGUF export
# (the converter outputs 0-tensor files). See V4_DEPLOY.md.
#
# Eyes v4 therefore runs the model directly in PyTorch via
# transformers + peft, quantized to int4 on CPU through optimum-quanto.
# That moves the heavy lifting from C++ (llama.cpp) to Python, but
# also removes the entire build toolchain from the image — no cmake,
# no gcc/g++, no curl/openssl headers. The runtime image is therefore
# slimmer than v3 despite carrying torch (~200 MB CPU wheel).
#
# Memory profile on Hetzner CPX32 (4 vCPU AMD, 8 GB RAM):
#   * int4 quanto weights : ~1.7 GB
#   * activations / KV    : ~0.6 GB (peak)
#   * python / FastAPI    : ~0.3 GB
#   * OS + docker engine  : ~0.5 GB
#   --------------------------------
#   Total peak            : ~3.1 GB
#   Headroom              : ~4.9 GB
# Matches the user's "runs on Raspberry Pi at Q4" mental model.

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    # Hugging Face caches go in a volume so model weights survive
    # container recreation. compose mounts ``models-cache`` here.
    HF_HOME=/models \
    TRANSFORMERS_CACHE=/models \
    # Pin BLAS threads to the host's vCPU count. CPX32 is 4 vCPU;
    # over-subscribing here just thrashes the cache.
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4

# --- OS dependencies -------------------------------------------------
# ffmpeg + libsndfile1 are required by librosa to decode the audio
# uploads on POST /transcribe. tini provides a real PID 1 so the
# container shuts down cleanly when supervisord sends SIGTERM.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      libsndfile1 \
      libgomp1 \
      curl \
      ca-certificates \
      tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps: install torch CPU FIRST ----------------------------
# Doing this in a separate layer keeps the (large, slow) torch download
# out of the requirements.txt rebuild path during dev. The +cpu wheel is
# ~180 MB vs. ~2 GB for the CUDA wheel — important on a hosted runner.
RUN pip install --upgrade pip \
 && pip install --prefer-binary \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      "torch==2.4.1+cpu"

COPY requirements.txt ./requirements.txt
RUN pip install --prefer-binary -r requirements.txt

# --- App code --------------------------------------------------------
COPY main.py ./main.py

# --- Runtime defaults ------------------------------------------------
ENV EYES_BASE_MODEL=google/gemma-4-E2B-it \
    EYES_ADAPTER_DIR=/adapter \
    EYES_QUANT=int4 \
    EYES_COMPUTE_DTYPE=bfloat16 \
    EYES_MAX_NEW_TOKENS=1024 \
    EYES_MAX_AUDIO_SECONDS=30 \
    EYES_GENERATE_TIMEOUT_S=180 \
    LOG_LEVEL=INFO \
    PORT=7860

EXPOSE 7860

# Healthcheck. First-boot is slow because we download Gemma-4 weights
# (~5 GB) on a cold cache. Once HF_HOME is warm in the mounted volume,
# subsequent restarts are ~30 s (load weights into RAM + apply LoRA).
# start-period therefore allows up to 15 min before we start failing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=900s --retries=3 \
  CMD curl -fsS http://localhost:7860/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# Single worker on purpose:
#  * the model lives in this process; multiple workers would each
#    duplicate the ~2 GB resident weights and OOM the host.
#  * concurrent generate() calls are serialised inside main.py via
#    asyncio.Lock — the FastAPI event loop handles request fan-in.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
