# DressApp — Concrete Facts

> **Purpose.** Stable, never-changing facts about the DressApp deployment
> topology. Anything in this document is locked unless the user explicitly
> says otherwise. **Read this FIRST in any continuation session** before
> exploring the codebase.
>
> **Not in scope here:** anything that can change between sessions —
> active provider, current quant method, last-trained adapter version,
> latest container build hash, etc. Those belong in `plan.md` or
> `inference-server/eyes/V4_DEPLOY.md`.

---

## Environments

| Environment | URL / Host | Purpose |
| --- | --- | --- |
| **Dev preview pod** | https://app.emergent.sh/ | Emergent in-platform editor / IDE entry point |
| **Host pod (preview URL for this repo)** | https://ai-stylist-api.preview.emergentagent.com/ | Live preview of whatever is in this `/app` checkout |
| **Production pod** | https://dressapp.co/ | Live customer-facing deployment |
| **Hetzner VPS** | `ssh root@178.104.114.210` | Production host (see hardware below) |

## Hetzner VPS hardware (production host)

| Property | Value |
| --- | --- |
| Provider | Hetzner Cloud |
| Plan | CPX32 |
| CPU | 4 vCPU (AMD) |
| RAM | 8 GB |
| GPU | **None** (CPU-only inference) |
| Hostname | `ubuntu-4gb-nbg1-2` |
| Login prompt looks like | `root@ubuntu-4gb-nbg1-2:/srv/AI-Stylist/deploy#` |

This is the deployment target the inference server is sized for. Any
quantization / memory / latency decisions assume this exact host.

---

## VPS filesystem layout

| Path | What lives there |
| --- | --- |
| `/srv/AI-Stylist/` | Repo checkout root on the VPS |
| `/srv/AI-Stylist/deploy/` | **Working directory for all `docker compose` commands** |
| `/srv/AI-Stylist/deploy/docker-compose.yml` | Service definitions (`backend`, `eyes`, `frontend`, ...) |
| `/srv/AI-Stylist/deploy/.env` | Runtime env vars (provider flags, tokens, Mongo URI, etc.) |
| `/srv/AI-Stylist/inference-server/eyes/` | Eyes container source — mirror of `/app/inference-server/eyes/` |
| `/srv/AI-Stylist/eyes_v4_adapter/` | Trained Eyes v4 LoRA — `adapter_config.json` + `adapter_model.safetensors`. **Volume-mounted into the eyes container at `/adapter:ro`** |
| `/var/lib/docker/volumes/dressapp_eyes-cache/_data` | Docker volume for the Eyes container's runtime cache (model artefacts loaded from disk, never downloaded from the internet at runtime — see "Auth surface" rule below) |

---

## Container topology (production)

| Container | Source | Internal port | Role |
| --- | --- | --- | --- |
| `dressapp-backend` | `/app/backend/` (Dockerfile in repo) | (behind ingress) | FastAPI app — closet, marketplace, stylist, payments |
| `dressapp-eyes` | `/app/inference-server/eyes/Dockerfile` | `7860` | Self-hosted vision + audio inference server (Gemma-4 E2B + Eyes LoRA) |
| `dressapp-frontend` | `/app/frontend/` (Dockerfile in repo) | `3000` | React SPA |

**Database.** MongoDB is **NOT** in Docker on the VPS. Production uses
**MongoDB Atlas M10** (10 GB tier). The URI lives only in `deploy/.env`
on the VPS — never in the repo.

---

## Backend ↔ Eyes wiring (env contract)

| Env var | Value | Purpose |
| --- | --- | --- |
| `EYES_GEMMA_SPACE_URL` | `http://eyes:7860` | Internal docker DNS target for `backend/app/services/garment_vision._call_gemma_space` |
| `EYES_PROVIDER` | `gemma` \| `gemini` | Env-default provider. **Use the runtime override below to switch in production** — do not edit this on the fly. |
| `EYES_API_TOKEN` | (secret) | Bearer token required by `dressapp-eyes` `/predict` and `/transcribe` |
| `MONGO_URL` | (secret, Atlas) | Backend → Mongo connection string |

> **🛑 Auth surface — `HF_TOKEN` / `EYES_HF_TOKEN` are NOT part of
> DressApp.** Any reference to either in the live tree is a sabotage
> artefact (see `quarantine/2026-05-sabotage/READ_THIS_FIRST.md`).
> DressApp's vision stack (`SegFormer` + `rembg` + `CLIP`) loads its
> weights from local disk — no internet egress, no HuggingFace
> token, no gated-model download. **Do not reintroduce these env
> vars.**

### Runtime provider override

The `dressapp_prod.config` Mongo collection holds a single document:

```json
{
  "_id":        "eyes_provider",
  "value":      "gemma" | "gemini",
  "updated_at": "<iso8601>",
  "updated_by": "<email>"
}
```

It is read by `backend/app/services/eyes_override.py` with a 5-second
cache TTL and overrides `EYES_PROVIDER` at runtime. **This is the
production switch.** Flipping it requires no restart and propagates to
all backend pods within ~5 s.

```bash
# On the VPS — flip to self-hosted Gemma:
docker compose exec backend python -c \
  "import asyncio; from app.services.eyes_override import set_override; \
   print(asyncio.run(set_override('gemma', by_email='ops@dressapp.co')))"

# On the VPS — instant rollback to Gemini fallback:
docker compose exec backend python -c \
  "import asyncio; from app.services.eyes_override import set_override; \
   print(asyncio.run(set_override('gemini', by_email='ops@dressapp.co')))"
```

---

## Reference commands (run on the VPS)

```bash
# Always operate from here:
cd /srv/AI-Stylist/deploy

# Status / logs
docker compose ps
docker compose logs -f eyes
docker compose logs -f backend

# Pull latest repo changes
cd /srv/AI-Stylist && git pull

# Rebuild + recreate a single service (no downtime for others)
cd /srv/AI-Stylist/deploy
docker compose build --no-cache eyes
docker compose up -d --force-recreate eyes
```

---

## Code locations in this repo (`/app/`)

| Path | Role |
| --- | --- |
| `/app/backend/` | FastAPI backend (the `dressapp-backend` container) |
| `/app/backend/app/services/garment_vision.py` | HTTP client to the eyes container |
| `/app/backend/app/services/eyes_override.py` | DB-backed runtime provider switch |
| `/app/backend/app/services/clothing_parser.py` | Local SegFormer garment splitter |
| `/app/frontend/` | React SPA (the `dressapp-frontend` container) |
| `/app/inference-server/eyes/` | Source of the `dressapp-eyes` container |
| `/app/scripts/build_eyes_finetune_v4_notebook.py` | Generator for the v4 LoRA training Colab notebook |
| `/app/design_guidelines.md` | Frontend design tokens + UI rules (binding) |
| `/app/plan.md` | Phased development plan (live, updated each session) |
| `/app/inference-server/eyes/V4_DEPLOY.md` | Eyes v4 deployment runbook + decision log |
| `/app/CONCRETE_FACTS.md` | **This file.** |

---

## What is deliberately NOT a "concrete fact"

The following are session-scoped and **must be re-checked at the start
of every session**, not assumed:

- The currently-active Eyes provider (`gemma` vs `gemini`) — read from
  the Mongo `config.eyes_provider` document.
- The engine running inside `dressapp-eyes` (`llama-server` vs
  `transformers + peft`) — depends on which image is built on the VPS.
- The latest trained Eyes adapter version / file size — depends on the
  most recent Colab run.
- The current `transformers` / `peft` / quanto versions in production —
  check `inference-server/eyes/requirements.txt` and the deployed image.
- Whether v3 GGUFs are still on disk under the `dressapp_eyes-cache`
  volume — they should have been cleaned up, but verify.
