# DressApp Eyes — Hetzner deploy

Self-hosted FastAPI wrapper around the fine-tuned **Gemma-4 E2B**
(`Yoram-Jacobs/dressapp-eyes-gguf` · `phase6-Q4_K_M.gguf`) used by the
DressApp closet pipeline. Replaces the Qwen-VL leg of
`backend/app/services/garment_vision.py` when `EYES_PROVIDER=gemma`.

Runs as a sibling container next to `backend`, `frontend`, and `caddy`
in `deploy/docker-compose.yml`. Internal-only: backend reaches it at
`http://eyes:7860` over the `dress` Docker network — Caddy never
proxies it, so it's never publicly exposed.

---

## ⚠️ RAM budget — read first

| Plan | Total | Backend (peak) | Caddy + frontend | Eyes (Q4_K_M, ~5 B) | Verdict |
|---|---|---|---|---|---|
| **CX22** | 4 GB  | ~1.4 GB | ~0.1 GB | ~4 GB resident | ❌ Will swap to disk hard. Boots, runs, but every `/predict` is 30 s+. |
| **CX32** | 8 GB  | ~1.4 GB | ~0.1 GB | ~4 GB resident | ✅ ~2 GB headroom. Comfortable. **Recommended.** |
| **CX42** | 16 GB | same    | same    | same | ✅ Future-proof for the Phase-2 mmproj (+1 GB) and bigger contexts. |

If you're staying on CX22 for now, add a 4 GB swap file before bringing
up the Eyes service:

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Upgrade to CX32 from the Hetzner console when convenient — the whole
migration is two clicks and ~30 s of downtime.

---

## One-time deploy

### 1. Pull latest code on the VPS

```bash
ssh root@<VPS_IP>
cd /srv/dressapp
git pull --ff-only origin main
```

### 2. Add three new keys to `deploy/.env`

```bash
$EDITOR deploy/.env
```

Append:

```
# ---- DressApp Eyes (Phase O.3) -------------------------------------
# Switches the closet vision pipeline from Qwen-VL to the self-hosted
# fine-tuned Gemma-4 E2B running in the eyes container.
EYES_PROVIDER=gemma
EYES_GEMMA_SPACE_URL=http://eyes:7860

# Read-only HF token scoped to Yoram-Jacobs/dressapp-eyes-gguf.
# Used ONCE on first eyes-container boot to download the GGUF; then
# never sent again. Rotate after the first successful boot.
EYES_HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Shared secret between the backend container and the eyes container.
# Generate with:  openssl rand -hex 32
EYES_API_TOKEN=replace-with-32-bytes-of-hex
```

### 3. Bring up the new service

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d --build eyes
```

First boot pulls the wheel index + the 3.4 GB GGUF — budget **5–10 min**
on the first run, then **~30 s** for every restart afterward (the GGUF
is cached in the `eyes-cache` named volume).

Watch the build + boot:

```bash
docker compose -f deploy/docker-compose.yml logs -f eyes
```

You should see, in order:

```
eyes  | downloading model: Yoram-Jacobs/dressapp-eyes-gguf/phase6-Q4_K_M.gguf
eyes  | downloaded /models/phase6-Q4_K_M.gguf (3.42 GB) in 92.4s
eyes  | loading model: /models/phase6-Q4_K_M.gguf (threads=2 ctx=4096)
eyes  | model ready in 18.3s (vision=False)
eyes  | INFO:     Uvicorn running on http://0.0.0.0:7860
```

### 4. Restart the backend so it picks up the new env

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d backend
```

The backend reads `EYES_PROVIDER`, `EYES_GEMMA_SPACE_URL`, and
`EYES_API_TOKEN` from `.env` at startup; existing items aren't
reanalysed, but every new `POST /api/v1/closet/analyze` (and the
`/reanalyze` button) now hits the local Eyes container instead of
Qwen-VL.

---

## Smoke test (run from the VPS)

```bash
# 1. Health (no auth required)
docker compose -f deploy/docker-compose.yml exec backend \
  curl -fsS http://eyes:7860/healthz
# Expect: {"status":"ok","model":"phase6-Q4_K_M.gguf","vision_enabled":false,...}

# 2. Inference (auth required)
TOKEN=$(grep ^EYES_API_TOKEN= deploy/.env | cut -d= -f2-)
docker compose -f deploy/docker-compose.yml exec backend \
  curl -fsS -X POST http://eyes:7860/predict \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Describe a navy blazer in JSON.","max_tokens":64,"json_mode":true}'
# Expect: {"output":"{\"category\":\"blazer\",...}","finish_reason":"stop",...}
```

## End-to-end test

Open the app, edit any closet item, click **Analyze**. The backend
should succeed (LLM call routed via the eyes container) and the
response latency will be ~5–15 s on CPU Basic. If it fails, the
backend's circuit breaker auto-falls-back to Qwen-VL — check
`docker compose logs backend | grep gemma` for any timeout/error
entries that triggered the fallback.

---

## Rotating the HF token

The HF token is only used for the **one-time GGUF download** on first
boot. Once `eyes-cache` has the file (verifiable with `docker volume
inspect dressapp_eyes-cache`), you can rotate or revoke the token at
any time without restarting anything. New tokens are only needed when:

- You push a new model file (`phase7-…gguf`) and want the next
  `docker compose up` to fetch it.
- You wipe the volume (`docker volume rm dressapp_eyes-cache`).

---

## Phase 2 — enable vision (mmproj)

When the vision projector exists in the model repo:

```
# add to deploy/.env
EYES_MMPROJ_FILE=mmproj-Gemma4E2B-f16.gguf
```

Then `docker compose up -d eyes`. The container detects the env var,
downloads the mmproj on next boot, and the FastAPI app auto-switches
to the `Llava15ChatHandler` — no other code change required.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Failed to load model from file: /models/...` | Wrong llama-cpp-python version. Confirm `requirements.txt` pins `0.3.16` or newer. Older versions don't know the Gemma-3/4 architecture. |
| `eyes` container OOM-kills (exit 137) at startup | Not enough RAM. Add swap (see top of file) or upgrade the VPS plan. |
| `eyes` healthy, but backend logs `gemma fallback` | Either `EYES_API_TOKEN` mismatch (backend `.env` ≠ eyes `.env`) or the model is taking too long. Check `EYES_GEMMA_TIMEOUT_S` (default 60s). |
| `huggingface_hub.utils._errors.RepositoryNotFoundError: 401` | HF token revoked / wrong scope. Issue a fresh **Read** token scoped to `Yoram-Jacobs/dressapp-eyes-gguf`, paste into `deploy/.env`, and `docker compose up -d eyes`. |
| `truncated download or LFS pointer file` | Network blip during the 3.4 GB pull. Wipe the cache and retry: `docker compose down eyes && docker volume rm dressapp_eyes-cache && docker compose up -d eyes`. |
| Building llama-cpp-python from source (long compile, then OOM) | Docker base image isn't `bookworm`. Confirm the first line of the Dockerfile is `FROM python:3.11-slim-bookworm` (NOT `slim` alone — that resolves to Trixie / glibc 2.41). |
