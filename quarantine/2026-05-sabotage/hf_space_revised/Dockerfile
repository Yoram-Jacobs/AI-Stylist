# syntax=docker/dockerfile:1.4
#
# HuggingFace Space — DressApp Eyes (Gemma-4 E2B, Q4_K_M)
# ========================================================
# CPU FREE TIER variant. Single-process Python container that
# embeds llama-cpp-python and exposes a FastAPI ``/predict``
# endpoint on port 7860 (the HF Spaces convention).
#
# Phase-1 deploy (the file you're reading)
# ----------------------------------------
# Pulls ONLY ``phase6-Q4_K_M.gguf`` (the fine-tuned LLM weights). The
# previous Dockerfile additionally pulled ``phase6-f16.gguf`` and
# tried to use it as the ``--mmproj`` vision projector — that's not
# what an mmproj file is (mmproj is a small dedicated vision encoder,
# typically 500 MB–1 GB) and llama.cpp rejects the F16 LLM weights as
# an mmproj. Without an mmproj file the model is text-only at the
# llama.cpp layer. Vision is auto-enabled in Phase 2 the moment a
# real ``mmproj-Gemma4E2B-f16.gguf`` is uploaded to the model repo
# (see the notebook cell ``Export multimodal projector (mmproj)``).
#
# Why we use a prebuilt wheel index
# ---------------------------------
# Building llama-cpp-python from source compiles llama.cpp's C++ in
# parallel (one g++ per vCPU) and peaks at 6–8 GB RAM. HF Spaces'
# free-tier build sandbox OOM-kills the process before it finishes
# (exit code 137 in the build log, no useful stack trace because the
# kernel SIGKILLs the whole process group).
#
# We dodge the compile entirely by pointing pip at the upstream
# project's prebuilt CPU wheel index:
#   https://abetlen.github.io/llama-cpp-python/whl/cpu
# Install drops from ~10 min + OOM to ~30 s and needs no toolchain.
#
# Deploy notes
# ------------
# * The model repo ``Yoram-Jacobs/dressapp-eyes-gguf`` is private, so
#   the build pulls weights using a BuildKit secret named
#   ``EYES_HF_TOKEN`` (Read scope on the repo). Configure it under
#   Space Settings → Secrets. Do NOT rename the secret — the build
#   mount below references it explicitly.
# * Public Space access: leave the visibility public.
#
FROM python:3.11-slim

# Slim toolchain: curl is needed for the runtime healthcheck. We
# DROP build-essential / cmake / git from the previous version
# because we're no longer compiling llama-cpp-python — the wheel
# from the upstream CPU index is binary-complete. This shrinks the
# image by ~450 MB and slashes build time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Working dir matches the standard HF Spaces layout.
WORKDIR /home/user/app

# ---- Python dependencies -------------------------------------------------
# ``--extra-index-url`` falls back to PyPI for everything except the
# ``llama-cpp-python`` wheel, which it pulls from abetlen's CPU
# wheel feed. ``--prefer-binary`` plus the explicit feed makes pip
# refuse to fall back to a source build even if PyPI's metadata is
# slightly newer.
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --prefer-binary \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
      -r requirements.txt

# ---- Application code ----------------------------------------------------
COPY app.py ./app.py
COPY README.md ./README.md

# ---- Download GGUF at build time -----------------------------------------
# Uses BuildKit secret so the token is mounted ONLY for this RUN step
# and is never written into a layer.
# https://docs.docker.com/build/building/secrets/
#
# We pull only the Q4_K_M weights (~3.4 GB). The F16 LLM and the
# (future) mmproj-*.gguf live in the same repo; uncomment the second
# download block below ONLY AFTER you've pushed the mmproj from the
# notebook. Trying to download a file that doesn't exist yet causes
# a silent build failure (HF truncates the 404 message).
ENV HF_HUB_ENABLE_HF_TRANSFER=0 \
    LLAMA_MODEL_PATH=/models/phase6-Q4_K_M.gguf

RUN --mount=type=secret,id=EYES_HF_TOKEN,required=true \
    HF_TOKEN="$(cat /run/secrets/EYES_HF_TOKEN)" \
    python -c "\
import os; \
from huggingface_hub import hf_hub_download; \
p = hf_hub_download( \
    repo_id='Yoram-Jacobs/dressapp-eyes-gguf', \
    filename='phase6-Q4_K_M.gguf', \
    local_dir='/models', \
    token=os.environ['HF_TOKEN']); \
print('downloaded:', p)" \
 && ls -lh /models

# ---- Phase 2: vision projector ------------------------------------------
# UNCOMMENT ONLY AFTER you have:
#   1. Run the notebook cell in MMPROJ_NOTEBOOK_CELL.md to extract
#      ``mmproj-Gemma4E2B-f16.gguf`` from the original safetensors.
#   2. Pushed the resulting mmproj file to
#      ``Yoram-Jacobs/dressapp-eyes-gguf``.
# Until both are done, leaving this block uncommented will fail the
# build with a 404 from huggingface_hub.
# RUN --mount=type=secret,id=EYES_HF_TOKEN,required=true \
#     HF_TOKEN="$(cat /run/secrets/EYES_HF_TOKEN)" \
#     python -c "\
# import os; \
# from huggingface_hub import hf_hub_download; \
# p = hf_hub_download( \
#     repo_id='Yoram-Jacobs/dressapp-eyes-gguf', \
#     filename='mmproj-Gemma4E2B-f16.gguf', \
#     local_dir='/models', \
#     token=os.environ['HF_TOKEN']); \
# print('downloaded mmproj:', p)"
# ENV LLAMA_MMPROJ_PATH=/models/mmproj-Gemma4E2B-f16.gguf

# ---- Runtime -------------------------------------------------------------
# llama-cpp-python's CPU build uses all available threads by default;
# we cap to 2 to match the free tier's 2 vCPU allocation. ``--workers 1``
# keeps the model loaded in a single process (no duplication) and
# matches llama.cpp's lack of true thread-safety on the same context.
ENV LLAMA_THREADS=2 \
    LLAMA_CTX_SIZE=4096 \
    LLAMA_N_BATCH=256 \
    PORT=7860

EXPOSE 7860

# Lightweight healthcheck — only counts the Space as healthy once
# /healthz returns 200, which only happens after the model is loaded.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://localhost:7860/healthz || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
