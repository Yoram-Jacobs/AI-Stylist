# DressApp Eyes — Hetzner deploy (CPU only).
#
# Build:  docker build -t dressapp-eyes .
# Run :   docker run -d --restart=always -p 7860:7860 \
#             -e EYES_HF_TOKEN=hf_xxx \
#             -e EYES_API_TOKEN=$(openssl rand -hex 32) \
#             -v eyes-cache:/models \
#             --name dressapp-eyes dressapp-eyes
#
# In production we run inside docker-compose (see deploy/docker-compose.yml)
# which sets all three env vars from deploy/.env and mounts the named
# volume eyes-cache so the GGUF download survives container rebuilds.
#
# Why python:3.11-slim-bookworm?
#   abetlen's prebuilt CPU wheels for llama-cpp-python target
#   manylinux_2_28 (glibc 2.28). Bookworm (Debian 12) ships glibc 2.36
#   which matches; Trixie (Debian 13, glibc 2.41) does NOT and forces
#   pip to fall back to a source build that needs gcc/cmake and
#   peaks at 6-8 GB RAM. That's exactly what OOM-killed the HF Space.
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0

# curl is needed for the HEALTHCHECK; ca-certificates for HTTPS pulls
# from huggingface.co at runtime. build-essential + cmake + git are a
# safety net for source-building llama-cpp-python if the prebuilt
# wheel index is ever down or missing the pinned version. With CPX32
# (4 dedicated vCPUs / 8 GB RAM) a fallback source build takes ~5 min
# and ~3 GB RAM peak — well within budget. The toolchain layer adds
# ~400 MB to the image but is fully cached after the first build.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates build-essential cmake git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps -----------------------------------------------------
# We compile llama-cpp-python from source. Reason: abetlen's prebuilt
# "linux_x86_64" wheels at https://abetlen.github.io/llama-cpp-python/whl/cpu
# are actually built against MUSL libc (Alpine), not glibc. Installing
# them on Debian / Ubuntu lands a binary that fails at import with
# "libc.musl-x86_64.so.1: cannot open shared object file" — exactly the
# trap we just hit. PyPI doesn't publish manylinux wheels for the
# Gemma-3-supporting versions either, so source compile is the only
# combination that produces a binary linked to the glibc this image
# actually has. CPX32 (4 dedicated vCPUs / 8 GB RAM) handles the
# compile in ~5 min; the resulting layer is fully cached afterwards.
#
# CMAKE_BUILD_PARALLEL_LEVEL pegs the build at 4 threads to use all
# CPX32 cores. Lower this on smaller plans (CX22's 2 vCPU / 4 GB RAM)
# to avoid OOM during the compile.
#
# CMAKE_ARGS:
#   -DGGML_NATIVE=OFF  → disable CPU-feature auto-detection so the
#                         resulting binary is portable across the
#                         AMD/Intel mix of Hetzner's fleet (avoids
#                         "Illegal instruction" if the host migrates).
#   -DGGML_BLAS=OFF    → don't link against system BLAS; the GGML
#                         built-in matmul is fast enough for CPU and
#                         skips the libopenblas / libmkl runtime dep.
COPY requirements.txt ./requirements.txt
ENV CMAKE_BUILD_PARALLEL_LEVEL=4 \
    CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_BLAS=OFF"
RUN pip install --upgrade pip \
 && pip install --no-binary llama-cpp-python -r requirements.txt

# --- App -------------------------------------------------------------
COPY main.py ./main.py

# --- Runtime defaults ------------------------------------------------
# /models is a Docker volume mount in compose; the GGUF gets pulled on
# first boot (lazy download in main.py) and cached forever after.
ENV EYES_MODEL_DIR=/models \
    EYES_MODEL_REPO=Yoram-Jacobs/dressapp-eyes-gguf \
    EYES_MODEL_FILE=phase6-Q4_K_M.gguf \
    LLAMA_THREADS=2 \
    LLAMA_CTX_SIZE=4096 \
    LLAMA_N_BATCH=256 \
    PORT=7860

EXPOSE 7860

# Don't mark healthy until the model is loaded AND the API responds.
# start_period covers GGUF download (~3.4 GB on first boot) + warm-up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD curl -fsS http://localhost:7860/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
