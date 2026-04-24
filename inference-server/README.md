# DressApp Inference Server

Self-hosted wrapper around the two MIT-licensed vision models used by the
DressApp closet pipeline (Phase V):

| Endpoint | Model | License | Purpose |
|---|---|---|---|
| `POST /segment-clothes` | `sayeed99/segformer_b3_clothes` | MIT | Per-class clothing segmentation (top / pants / dress / shoes / …). |
| `POST /remove-background` | `ZhengPeng7/BiRefNet` | MIT | Non-generative alpha matting (no hallucination). |
| `GET /healthz` | — | — | Liveness probe. |

Drop-in replacement for Hugging Face Inference API — same JSON shape our
FastAPI backend already consumes. Once deployed, wire it in by setting:

```
CLOTHING_PARSER_ENDPOINT_URL=https://models.dressapp.co
BACKGROUND_MATTING_ENDPOINT_URL=https://models.dressapp.co
```

in `/app/backend/.env` on the DressApp app.

---

## Hardware

Recommended: **1× NVIDIA L4 or T4 (24 GB)** — enough for both models
resident + ~100 concurrent requests/min.
Minimum: any CUDA-capable GPU with ≥ 8 GB VRAM.
CPU-only: works but matting takes ~3 s/image instead of ~120 ms.

---

## Quick deploy

### Modal (fastest)

```bash
pip install modal
modal deploy inference-server/modal_deploy.py  # see separate template
```

### RunPod / Lambda Labs / any GPU VM

```bash
git clone <your fork>
cd inference-server
docker build --build-arg HF_TOKEN=hf_xxx -t dressapp-inference .
docker run -d --gpus all --restart=always -p 8000:8000 \
    -e INFERENCE_API_TOKEN=<long-random-string> \
    --name dressapp-inference dressapp-inference
```

Put a TLS terminator in front (Caddy, Nginx, or Cloudflare) and point
`models.dressapp.co` at it.

---

## Auth

Set `INFERENCE_API_TOKEN` to any long random string in the environment.
All endpoints require `Authorization: Bearer <token>`. Leave the env var
blank for local development (no auth).

The DressApp backend sends `HF_TOKEN` today (HF Inference API path) — when
switching to self-hosted, we'll pass `INFERENCE_API_TOKEN` instead. That
wiring is one line in the two service modules (`clothing_parser.py` and
`background_matting.py`).

---

## API contracts

### `POST /segment-clothes`

- **Body**: `multipart/form-data` with field `image` (JPEG or PNG).
- **Response**: `200 OK`
  ```json
  {
    "segments": [
      {
        "label": "Upper-clothes",
        "score": 1.0,
        "mask": "data:image/png;base64,..."
      },
      { "label": "Pants", "score": 1.0, "mask": "..." }
    ]
  }
  ```

### `POST /remove-background`

- **Body**: `multipart/form-data` with field `image`.
- **Response**: `200 OK`
  ```json
  { "image_png_b64": "iVBORw0KGgoAAAA..." }
  ```

---

## Scaling

- **Stateless** — can run N replicas behind a load balancer.
- **GPU-pinned**: models are loaded once at container start. First
  request after boot is slow (~8 s); subsequent requests are fast.
- **Batch size** for segment-clothes is 1 in this MVP. If you want batch
  processing, edit `main.py` to accept multiple files per request.

---

## Monitoring

- `/healthz` returns device + model info. Wire to uptime-robot or K8s
  readiness probe.
- Logs are on stdout; ship to Datadog / Grafana Loki / CloudWatch as
  usual.
- Latency target: `segment-clothes` < 300 ms p50 on L4, `remove-background`
  < 250 ms p50.

---

## Roll-forward / roll-back plan

The DressApp backend already supports **graceful fallback**:

1. Try self-hosted endpoint (if `*_ENDPOINT_URL` set).
2. Try HF Inference API (if `HF_TOKEN` set).
3. Fall back to the legacy Gemini bbox detector.

So you can deploy this service, flip the env var, and roll back instantly
by clearing the env var — no code changes needed on the DressApp side.
