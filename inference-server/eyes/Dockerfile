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
# from huggingface.co at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python deps -----------------------------------------------------
# --extra-index-url pulls llama-cpp-python from the maintainer's CPU
# wheel feed. PyPI is still consulted for everything else.
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
 && pip install --prefer-binary \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
      -r requirements.txt

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
