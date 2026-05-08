# DressApp Eyes (Gemma-4 E2B GGUF) — CPU-only Hetzner deploy.
#
# ARCHITECTURE NOTE — why we don't use llama-cpp-python any more.
# ===============================================================
# Your fine-tune base is ``unsloth/gemma-4-e2b-it-unsloth-bnb-4bit``
# (Google Gemma 4, April 2026). The GGUF metadata pre-flight confirmed
# ``general.architecture: 'gemma4'``. Gemma 4 support landed in
# llama.cpp mainline via Unsloth's PR #21343, but ``llama-cpp-python``
# wheels (latest 0.3.22 at time of writing) bundle a llama.cpp commit
# from BEFORE that merge — its loader rejects gemma4 GGUFs with the
# generic "Failed to load model from file".
#
# Rather than wait for a llama-cpp-python release that catches up, we
# build ``llama-server`` from llama.cpp HEAD ourselves and run it as
# the actual inference engine. main.py becomes a thin FastAPI proxy
# that forwards our existing ``/predict`` contract onto llama-server's
# OpenAI-compatible ``/v1/chat/completions`` endpoint — backend's
# ``garment_vision._call_gemma_space`` is therefore unchanged.
#
# Multi-stage build:
#   Stage 1 (builder)  — full toolchain, compiles llama-server.
#   Stage 2 (runtime)  — slim Python image, just the binary + proxy.
#
# This keeps the runtime image small (~250 MB) while building llama.cpp
# in isolation. CPX32's 4 dedicated AMD vCPUs compile it in ~5 min;
# the layer is then cached for subsequent rebuilds.

# =============================================================
# Stage 1 — build llama-server from llama.cpp mainline.
# =============================================================
FROM debian:bookworm-slim AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential cmake git curl ca-certificates \
      libcurl4-openssl-dev pkg-config \
 && rm -rf /var/lib/apt/lists/*

# Pin to a specific commit so the build is reproducible. Update by
# bumping LLAMA_CPP_REF and rebuilding. ``master`` is the mainline.
# We pick master here because gemma4 support is recent (post Apr 2026)
# and we want to track upstream until it's clearly stable. Once Gemma 4
# fixes settle, pin to a specific commit hash for reproducibility.
ARG LLAMA_CPP_REF=master

WORKDIR /src
RUN git clone --depth=1 --branch ${LLAMA_CPP_REF} \
      https://github.com/ggml-org/llama.cpp.git

WORKDIR /src/llama.cpp

# Build flags:
#   GGML_NATIVE=OFF        — portable binary, doesn't pin to host CPU
#                             features (Hetzner may migrate the host).
#   GGML_BLAS=OFF          — skip system BLAS, GGML's built-in is fine
#                             for CPU and avoids the libopenblas dep.
#   LLAMA_BUILD_TESTS=OFF  — skip test binaries.
#   LLAMA_BUILD_EXAMPLES=OFF — we only need llama-server.
#   LLAMA_CURL=ON          — enables ``-hf`` direct HuggingFace pulls
#                             (we don't use this here — Python proxy
#                             handles the download — but it's free).
RUN cmake -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DGGML_NATIVE=OFF \
      -DGGML_BLAS=OFF \
      -DLLAMA_BUILD_TESTS=OFF \
      -DLLAMA_BUILD_EXAMPLES=OFF \
      -DLLAMA_CURL=ON \
 && cmake --build build --config Release \
      --target llama-server \
      -j 4

# =============================================================
# Stage 2 — slim runtime.
# =============================================================
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0

# Runtime deps:
#   curl              — HEALTHCHECK + admin smoke tests.
#   libgomp1          — OpenMP runtime, llama.cpp links against it.
#   libcurl4          — required by llama-server when built with LLAMA_CURL=ON.
#   ca-certificates   — HTTPS to huggingface.co for GGUF download.
#   tini              — proper PID 1, reaps the llama-server child cleanly.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl libgomp1 libcurl4 ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

# Pull the freshly-built binary from the builder stage. We deliberately
# don't copy the whole /src tree — just the one binary we need.
COPY --from=builder /src/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server
RUN chmod +x /usr/local/bin/llama-server \
 && /usr/local/bin/llama-server --version || true

WORKDIR /app

# --- Python deps for the proxy ---------------------------------------
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
 && pip install --prefer-binary -r requirements.txt

# --- App code --------------------------------------------------------
COPY main.py ./main.py

# --- Runtime defaults -----------------------------------------------
ENV EYES_MODEL_DIR=/models \
    EYES_MODEL_REPO=Yoram-Jacobs/dressapp-eyes-gguf \
    EYES_MODEL_FILE=phase6-Q4_K_M.gguf \
    LLAMA_THREADS=2 \
    LLAMA_CTX_SIZE=4096 \
    LLAMA_N_BATCH=256 \
    LLAMA_INTERNAL_PORT=8080 \
    PORT=7860

EXPOSE 7860

# Healthcheck waits up to 10 minutes on first boot (GGUF download +
# llama-server warm-up). After that, restarts are <1 min.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD curl -fsS http://localhost:7860/healthz || exit 1

# tini reaps the llama-server child if uvicorn exits, preventing a
# zombie process from holding 4 GB of RAM after a crash.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
