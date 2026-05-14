# Preview pod vs. Hetzner production — what's different, and why

> **Read this BEFORE filing any "the Eyes aren't working" or "everything is
> falling back to Gemini" bug.** Most such bugs in the preview environment
> are *expected behaviour*, not regressions.

The DressApp codebase deploys to two materially different environments:

| | Emergent preview pod (this container) | Hetzner production (`dressapp.co`) |
|---|---|---|
| **Topology** | Single Kubernetes pod, no sidecars | Docker Compose stack with named services |
| **Backend reaches Eyes via** | nothing — there is no `eyes` service on this network | `http://eyes:7860` (internal Docker DNS) |
| **`EYES_PROVIDER`** | `gemini` | `gemma` |
| **`EYES_GEMMA_SPACE_URL`** | blank | `http://eyes:7860` |
| **AddItem analysis served by** | **Gemini 2.5 Flash directly** | **Self-hosted Gemma 4 E2B GGUF**, Gemini only as safety fallback |
| **SegFormer (clothing parser)** | Local, in-process, CPU | Local, in-process, CPU |
| **rembg matting** | Local, in-process, CPU | Local, in-process, CPU |
| **Nano Banana (reconstruction)** | Direct Gemini via `GEMINI_API_KEY` | Direct Gemini via `GEMINI_API_KEY` |
| **Mongo** | `test_database` on the local mongod | `dressapp_prod` on Atlas |

## Why preview can never use Gemma

There is no `dressapp-eyes` container on the preview pod's network. The
`docker-compose.yml` and the Gemma 4 E2B GGUF (~4.8 GB) only exist on
the Hetzner box. Trying to dial `http://eyes:7860` from preview returns
DNS-NXDOMAIN immediately; trying to dial the *old* Hugging Face Space
(`https://yoram-jacobs-dressapp-eyes-gguf.hf.space`) returns 503
("Space is paused") since the May-2026 migration.

The preview env is therefore **pinned to `EYES_PROVIDER=gemini`** in
`/app/backend/.env`. The DB-backed `eyes_override` is also cleared so
no stale toggle can redirect into a dead path.

## Symptoms you can safely ignore in preview

| Symptom | Meaning | Action |
|---|---|---|
| `provider=gemini fallback=False routing=toggle` in logs | Expected. Direct Gemini path, no Gemma attempt. | None |
| Eyes call returns in 5-10s instead of 15-25s | Expected — preview skips the Hetzner round-trip | None |
| `eyes_override doc = null` in `config` collection | Expected — preview has no override, falls through to env-default | None |
| `dressapp-eyes` container missing from `docker ps` | Expected — preview is not a Compose stack | None |
| `curl https://yoram-jacobs-dressapp-eyes-gguf.hf.space/healthz` → 503 | Expected — the HF Space has been paused since the Hetzner migration. Do **not** restart it. | None |

## Symptoms that ARE bugs in preview

| Symptom | Possible cause | First debug step |
|---|---|---|
| `provider=gemma` in logs | Something resurrected the Gemma toggle | `db.config.find_one({_id:"eyes_provider"})` — should be `None`; if not, delete it |
| `fallback=True` in logs | Backend tried Gemma anyway. The env wasn't reloaded after `.env` change | `supervisorctl restart backend` |
| Eyes call hangs 60s before responding | Same — Gemma timeout wait. Check `EYES_PROVIDER` resolves to `gemini` via `eyes_override.get_active_provider()` | As above |
| HTTP 503 from `/api/v1/closet/analyze` | `garment_vision_service is None` — likely missing `GEMINI_API_KEY` or `EMERGENT_LLM_KEY` | Check `settings.gemini_chat_key` is set |

## Symptoms that ARE bugs in production

| Symptom | First debug step |
|---|---|
| `provider=gemini fallback=True` | `dressapp-eyes` container is unhealthy or not reachable from backend. `docker compose -f deploy/docker-compose.yml ps eyes` and check its logs. |
| Eyes call hangs 60s | Same. The container is alive but the model didn't load. Check `EYES_LLAMA_*` env vars and `/var/lib/docker/volumes/dressapp_eyes-cache`. |
| HTTP 503 from `/api/v1/closet/analyze` | `garment_vision_service is None` — check `GEMINI_API_KEY` is set in `deploy/.env` (used by the fallback path too). |

## How to test prod-style behaviour locally

If you really need to test the Gemma path from a non-Hetzner machine:

```bash
# from /app (laptop with docker)
cp deploy/.env.example deploy/.env
# fill in: EYES_API_TOKEN (openssl rand -hex 32), EYES_HF_TOKEN, GEMINI_API_KEY,
#         MONGO_URL pointing to a local mongo, etc.
docker compose -f deploy/docker-compose.yml up -d --build eyes backend
docker compose -f deploy/docker-compose.yml logs -f eyes
# wait for "Application startup complete" + "/healthz 200" in the eyes logs (cold ≈ 90s)
curl -s http://localhost:8001/api/v1/closet/analyze/version | jq
```

## Provider matrix (what's authoritative where)

```
                   ┌───────────────────────┐
backend env    ──► │ settings.EYES_PROVIDER│ (cold-default; env-only fallback)
                   └─────────┬─────────────┘
                             │
Mongo override ──► ┌─────────▼─────────────────────┐
config.eyes_provider │ eyes_override.get_active(...) │ ◄── 5s TTL cache
                   └─────────┬─────────────────────┘
                             │
                   ┌─────────▼─────────────────────┐
                   │ garment_vision.analyze(...)   │
                   │   if resolved=="gemma"        │
                   │     → _call_gemma_space()     │ ── http://eyes:7860 (prod only)
                   │     on error → cascade ↓      │
                   │   else (gemini / any other)   │
                   │     → emergentintegrations    │ ── Gemini 2.5 Flash
                   │       LlmChat (.with_model)   │
                   └───────────────────────────────┘
```

`_VALID_PROVIDERS` in `eyes_override.py` is `("gemma", "gemini")`. Any
other persisted value (legacy `"qwen"`, typos, etc.) returns `None`
from `_normalize` and falls through to the env default — which is
itself sanitised the same way.

## Lessons from earlier agent sessions

These all caused wasted-credit incidents in past sessions and have now
been physically fixed in the repo:

1. **The HF Space URL was hard-coded in preview `.env`** even after the
   Hetzner migration. Reading the preview env made it look like Eyes
   was still on HF. Status: preview `.env` now blanks the URL and pins
   `EYES_PROVIDER=gemini`.

2. **`QWEN_EYES_MODEL` and `EYES_PROVIDER=qwen` were left in
   `config.py` defaults** even though Qwen-Eyes was never enabled.
   Agents kept "discovering" Qwen and trying to wire it in. Status:
   removed in May-2026. `_VALID_PROVIDERS` already excluded `qwen`,
   so the cleanup is defense-in-depth.

3. **`_hf_chat_json()` was dead code referenced only by itself.**
   Agents kept treating it as part of the active Eyes path. Status:
   deleted in May-2026.

4. **DB override `config.{_id:"eyes_provider", value:"gemma"}` was set
   in the preview DB**, but preview cannot reach Gemma. Every call
   waited 60s, then fell back. Status: cleared from `test_database`.

If you find yourself reading any of those four artefacts in a future
session, treat it as a regression — they were deliberately removed.
