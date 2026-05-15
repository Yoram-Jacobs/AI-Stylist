# DressApp inference server — deploy on any NVIDIA GPU host.
# Tested on: Ubuntu 22.04 + CUDA 12.1.
#
# Build:  docker build -t dressapp-inference .
# Run:    docker run --gpus all -p 8000:8000 \
#             -e INFERENCE_API_TOKEN=change-me \
#             dressapp-inference

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip python3.10-venv git curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cu121 \
        torch torchvision \
    && pip install -r requirements.txt

COPY main.py .

# Warm model cache at build time so container cold-start is fast.
# The models below (``sayeed99/segformer_b3_clothes`` and
# ``ZhengPeng7/BiRefNet``) are **public, non-gated** on HuggingFace.
# No ``HF_TOKEN`` ``ARG`` / ``ENV`` is needed for this step — the
# previous Dockerfile passed one only to placate a misconfigured
# build pipeline. See ``quarantine/2026-05-sabotage/READ_THIS_FIRST.md``.
RUN python -c "from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor; \
    SegformerImageProcessor.from_pretrained('sayeed99/segformer_b3_clothes'); \
    AutoModelForSemanticSegmentation.from_pretrained('sayeed99/segformer_b3_clothes'); \
    AutoModelForSemanticSegmentation.from_pretrained('ZhengPeng7/BiRefNet', trust_remote_code=True)"

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
