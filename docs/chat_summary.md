# Phase O.3 — DressApp Eyes Deploy Chat Summary

This document captures the May 2026 working session that migrated the
self-hosted vision model ("Eyes") from a HuggingFace Space deploy to a
Hetzner CPX32 VPS, and added an admin runtime toggle for switching
between the legacy Qwen-VL cloud path and the new Gemma-4 endpoint.

The goal of writing this down is twofold:

1. Future engineers (or future-you) can read one file and understand
   *why* the deploy looks the way it does — every architectural choice
   below was forced by a real failure we hit and worked around.
2. If something breaks on the VPS later, the troubleshooting matrix at
   the bottom maps each historical failure mode to its root cause and
   the file that was changed to fix it.

---

## 1. Starting state

* The Eyes model was being served from a HuggingFace Space at
  `Yoram-Jacobs/dressapp-eyes-gguf` *(Space, not the model repo of the
  same name)*. Build was failing.
* Backend already had the `EYES_PROVIDER` / `EYES_GEMMA_SPACE_URL` env
  flags wired into `garment_vision._call_gemma_space` with circuit-
  breaker fallback to Qwen-VL.
* The fine-tuned model is **Google Gemma-4 E2B-IT** (released April 2026,
  base: `unsloth/gemma-4-e2b-it-unsloth-bnb-4bit`), LoRA-merged to FP16
  then quantised to **Q4_K_M** (~3.18 GB GGUF).

---

## 2. Failure trail — HuggingFace Space attempts

| # | Symptom | Root cause | Fix attempted |
|---|---|---|---|
| 1 | `secret EYES_HF_TOKEN: not found` during build | HF Settings UI bug — Secrets section refused to save the value | Switch to a public **Variable** (HF auto-forwards Variables as `--build-arg`s); written `Dockerfile.arg-fallback` |
| 2 | Variable form rejected the name `EYES-HF-TOKEN` | HF regex `^[a-zA-Z][_a-zA-Z0-9]*$` rejects hyphens | Renamed to `EYES_HF_TOKEN` (underscores) |
| 3 | Build silently terminated after `pip install` | Source-compiling `llama-cpp-python==0.3.5` peaked at 6–8 GB RAM; HF's free build sandbox OOM-killed the process (no log surfaced) | Switched to `llama-cpp-python==0.3.16` from abetlen's prebuilt CPU wheel index (`https://abetlen.github.io/llama-cpp-python/whl/cpu`) |
| 4 | Build still tried to compile from source — `Could not find compiler: gcc` | abetlen's index has wheels for 0.3.18/0.3.19 but **not** 0.3.16 → pip fell back to source dist; we'd removed the toolchain to "save space" | Bumped to `llama-cpp-python==0.3.19`, kept the toolchain available for fallback compiles |
| 5 | Container started but failed at runtime: `OSError: libc.musl-x86_64.so.1: cannot open shared object file` | abetlen's "linux_x86_64" wheel is **secretly built against MUSL/Alpine**, not glibc. Installs cleanly on Debian, fails at first `dlopen` | Switched to `pip install --no-binary llama-cpp-python …` to compile from source on the target host |

After failure #5 the user disengaged from the HF Space approach and
decided to host on their own infrastructure.

---

## 3. Pivot — switch to Hetzner VPS

The user's app already runs on a Hetzner CX22 at `dressapp.co` (see
`HETZNER_RECOVERY.md` and `deploy/DEPLOY.md`). All services are managed
by `docker compose` behind a Caddy TLS terminator. We added Eyes as a
fourth `dress`-network service so the backend reaches it at
`http://eyes:7860` (internal-only — Caddy never proxies it).

### Server-spec progression

| Plan | vCPU | RAM | Disk | Verdict |
|---|---|---|---|---|
| CX22 (initial) | 2 shared | 4 GB | 38 GB | Too small — Q4_K_M of a ~5B Gemma-4 needs ~4 GB resident RAM alone, leaving the 1.4 GB-peak backend fighting Mongo for the rest. Compile of llama.cpp also marginal. |
| **CPX32 (final)** | **4 dedicated AMD EPYC** | **8 GB** | **75 GB** | Comfortable. ~2× inference throughput vs CX32 thanks to dedicated cores; enough disk for compile scratch + the 3.4 GB GGUF + image layers. **Recommended.** |

A subtle gotcha that bit us: Hetzner resizes only finish after a full
**panel-side power-off-then-on**, not an OS-level `reboot`. The hostname
`ubuntu-4gb-nbg1-2` lingered after the resize and confused diagnosis
until `nproc=4` and `free -h ≈ 8 Gi` confirmed the new hardware.

---

## 4. Failure trail — Hetzner VPS attempts

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 6 | `Could not resolve host: eyes` from `backend` | `backend` container was created **before** the `eyes` service was added to `docker-compose.yml`; its network membership was stale | `docker compose up -d --force-recreate backend` |
| 7 | `dressapp-eyes` stuck in `Restarting (3)` loop | `Failed to load model from file` — opaque llama.cpp error | Added a pure-Python **GGUF metadata sniffer** to `main.py` that logs `general.architecture` *before* attempting to load. Result: `general.architecture: 'gemma4'` — confirmed it's not Gemma 3n, not Gemma 3, but the brand-new **Gemma 4** architecture from Google's April 2026 release |
| 8 | `apt: not enough free space in /var/cache/apt/archives/` during `docker build` | Disk pressure: leftover image layers from earlier builds + CX22's small disk; resize hadn't been finalised yet | `docker system prune -af && docker builder prune -af` (reclaimed 4.7 GB), plus the panel power-cycle to land the CPX32 disk |

### The real diagnosis behind failure #7

The user's adapter config (`models/pog_phase6/pog_phase6_model/adapter_config.json`)
explicitly lists:

```json
{
  "base_model_name_or_path": "unsloth/gemma-4-e2b-it-unsloth-bnb-4bit",
  "auto_mapping": {
    "base_model_class": "Gemma4ForConditionalGeneration",
    "parent_library": "transformers.models.gemma4.modeling_gemma4"
  }
}
```

— so this is genuinely Gemma 4, *not* Gemma 3n (the `E2B` suffix exists
in both lineages, which initially threw me off). Gemma 4 support landed
in `llama.cpp` mainline via Unsloth's PR #21343. **However**, the
`llama-cpp-python` package bundles a llama.cpp commit from *before* that
merge — even the latest 0.3.22 wheel can't load `gemma4` GGUFs.

The pragmatic fix: drop the Python binding entirely and run
`llama-server` built directly from `llama.cpp` HEAD.

---

## 5. Final architecture

```
┌─────────────────── docker compose project (network: dress) ────────────────────┐
│                                                                                 │
│   ┌──────────┐    HTTPS    ┌──────────┐    /api/*    ┌────────────┐             │
│   │ Internet ├────────────►│  caddy   ├─────────────►│  backend   │             │
│   └──────────┘             │ (TLS)    │              │ (FastAPI)  │             │
│                            └────┬─────┘              └────┬───────┘             │
│                                 │ /                       │                     │
│                                 ▼                         │ http://eyes:7860    │
│                            ┌──────────┐                   │ Bearer EYES_API_TOKEN│
│                            │ frontend │                   │                     │
│                            │ (nginx)  │                   ▼                     │
│                            └──────────┘            ┌──────────────┐             │
│                                                    │   eyes       │             │
│                                                    │  (FastAPI)   │             │
│                                                    │  /predict    │             │
│                                                    └──────┬───────┘             │
│                                                           │ http://127.0.0.1:8080 │
│                                                           │ (loopback only)     │
│                                                           ▼                     │
│                                                    ┌──────────────┐             │
│                                                    │ llama-server │  spawned by │
│                                                    │ (built from  │  main.py at │
│                                                    │  llama.cpp   │  startup    │
│                                                    │   HEAD)      │             │
│                                                    └──────────────┘             │
│                                                           │                     │
│                                                           ▼                     │
│                                                    /models/phase6-Q4_K_M.gguf   │
│                                                    (volume: eyes-cache)         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Container internals (`inference-server/eyes/`)

* **`Dockerfile`** — multi-stage. Stage 1 (`debian:bookworm-slim`)
  installs build-essential + cmake + git + libcurl, clones llama.cpp
  HEAD, and compiles `llama-server` only with `GGML_NATIVE=OFF`
  (portable binary), `GGML_BLAS=OFF` (skip system BLAS), and `-j 4`.
  Stage 2 (`python:3.11-slim-bookworm`) is the runtime: copies just
  `/usr/local/bin/llama-server` out of stage 1, installs the proxy's
  Python deps, and runs under `tini` so the llama-server child is
  reaped on shutdown. Final image ~250 MB.
* **`main.py`** — FastAPI proxy. `lifespan` lazy-downloads the GGUF
  from the private HF repo on first boot (cached afterwards in the
  `eyes-cache` named volume), runs the metadata sniffer, spawns
  `llama-server` on `127.0.0.1:8080`, polls its `/health` until ready,
  then yields. `/predict` translates our custom JSON shape to and
  from OpenAI's `/v1/chat/completions` (which is what `llama-server`
  natively speaks). `/healthz` 503s until llama-server is loaded.
* **`requirements.txt`** — only `fastapi`, `uvicorn[standard]`,
  `pydantic`, `huggingface_hub`, `httpx`. No more `llama-cpp-python`.

### Backend integration (unchanged contract)

`garment_vision._call_gemma_space` continues to send our custom
`/predict` payload with `Authorization: Bearer ${EYES_API_TOKEN}`.
The proxy hides the OpenAI translation entirely.

`config.py` gained two settings: `EYES_API_TOKEN` (preferred bearer
for `_call_gemma_space`, falls back to `EYES_HF_TOKEN` for legacy
HF-Space deploys) and `ADMIN_EMAILS` (comma-separated list, gates the
Developer panel).

---

## 6. New feature — runtime Eyes-provider toggle (admin-only)

Implemented because flipping `EYES_PROVIDER` via `.env` requires a
backend container restart, and the user wanted to A/B between Qwen and
Gemma without redeploying. Per the requirements call:

* **Where:** Profile → Settings → "Developer / Internal" accordion.
* **Visibility:** admin-gated by role (admin role is granted when the
  logged-in email matches `ADMIN_EMAILS` env, plus the hardcoded
  `dev@dressapp.io` dev-bypass user).
* **Scope:** per-pod. Each pod's `config.{_id: "eyes_provider"}`
  document is independent. Hetzner-prod's `dressapp_prod` and the
  Emergent preview's `test_db` carry separate overrides.
* **Persistence:** survives container restart (Mongo-backed).
* **Resolution order on every analyse call:** Mongo override (5 s
  cache) → env default → `qwen` (final fallback).

### New backend module — `services/eyes_override.py`

Single source of truth for "which provider should this analyse call
use right now". 5-second module-level cache to avoid hot-path DB hits;
cache busts immediately on `set_override()`. Fail-closed: any DB error
falls through to the env default so the closet pipeline never breaks
because of the override layer.

### New admin endpoints (`api/v1/admin.py`)

* `GET /api/v1/admin/eyes` — current state + last 5 garment-vision
  calls from `provider_activity`.
* `POST /api/v1/admin/eyes` `{provider: "gemma" | "qwen" | null}` —
  set or clear the override. Audit-logs `updated_by` (admin email).

### Frontend — `components/DeveloperPanel.jsx`

A self-contained component slotted at the bottom of `pages/Profile.jsx`.
Renders nothing for non-admin users (the gate is internal). When
admin, shows:

* Active provider line + source badge (`env default` vs `DB override`)
* Toggle switch (Qwen ↔ Gemma) with optimistic UI
* Two wiring sanity flags — Gemma URL set?, Bearer token set?
* Last-call summary (provider, latency, ok/err, relative age)
* Refresh button + Clear-override button (auto-disabled when nothing
  to clear)
* Sonner toast on every successful flip

Uses the existing `api.adminEyesStatus()` / `api.adminEyesSet()`
helpers in `lib/api.js`.

---

## 7. Files added / changed in this session

### Added

* `inference-server/eyes/Dockerfile` — multi-stage llama-server build
* `inference-server/eyes/main.py` — FastAPI proxy in front of llama-server
* `inference-server/eyes/requirements.txt`
* `inference-server/eyes/README.md` — deploy runbook + RAM budget matrix + troubleshooting
* `backend/app/services/eyes_override.py` — DB-backed provider override resolver
* `frontend/src/components/DeveloperPanel.jsx` — admin-only Profile panel
* `docs/chat_summary.md` — *this document*

### Modified

* `deploy/docker-compose.yml` — new `eyes` service on `dress` network + `eyes-cache` volume
* `backend/app/config.py` — new `EYES_API_TOKEN` field
* `backend/app/services/garment_vision.py` — `_call_gemma_space` now resolves provider via `eyes_override.get_active_provider()`; bearer source prefers `EYES_API_TOKEN` over `EYES_HF_TOKEN`
* `backend/app/api/v1/admin.py` — `GET` / `POST /admin/eyes` endpoints
* `frontend/src/pages/Profile.jsx` — slotted `DeveloperPanel` at end of Settings
* `frontend/src/lib/api.js` — `adminEyesStatus()` / `adminEyesSet()` helpers

### Discarded along the way (kept in this doc for context)

* `hf_space_revised/Dockerfile` and `Dockerfile.arg-fallback` — both
  HuggingFace Space variants. Superseded by the Hetzner deploy.
* `hf_space_revised/MMPROJ_NOTEBOOK_CELL.md` — instructions for
  extracting the vision projector. Still relevant for Phase 2 (vision)
  whenever the projector is pushed to the model repo.

---

## 8. Operational notes & gotchas

* **Always run `docker compose` from the project root** (`/srv/AI-Stylist`),
  never from inside `deploy/`. Otherwise `--env-file deploy/.env`
  resolves to `deploy/deploy/.env` and fails. Wasted ~15 min on this.
* **`git pull` says "Already up to date"** until you actually push
  from the Emergent dev environment. Always `grep` for a known marker
  in the file you expect to have changed before rebuilding:
  `grep "AS builder" inference-server/eyes/Dockerfile`.
* **`docker compose up -d --build eyes` reuses cached layers**.
  When swapping the engine (e.g., this session's pivot from
  `llama-cpp-python` to `llama-server`), use `build --no-cache eyes`
  or you'll get the old broken image again.
* **First-boot timing on CPX32:** ~5 min cmake compile of llama.cpp
  + ~90 s GGUF download + ~12 s model load = **~7–10 min**. After
  that, restarts are <1 min (compile layer cached, GGUF cached).
* **Hetzner resize lifecycle:** the panel resize grants resources, but
  the disk only grows after a panel-driven **power off → power on**.
  An in-VM `reboot` doesn't trigger it. Verify with `df -h /` and
  `nproc`. The hostname doesn't auto-update.
* **HF token rotation:** the read-only HF token is only used by the
  eyes container at first boot to download the GGUF. Once the file
  lives in the `eyes-cache` volume, the token can be rotated /
  revoked without affecting runtime. Leaked tokens (one was
  exposed in a screenshot earlier this session) **must be revoked
  immediately**.

---

## 9. Troubleshooting matrix

| Log line | Meaning | Fix |
|---|---|---|
| `Could not resolve host: eyes` (from backend) | Backend container predates the addition of the `eyes` service | `docker compose up -d --force-recreate backend` |
| `secret EYES_HF_TOKEN: not found` (HF Space) | HF Secrets UI bug | Use a Variable + ARG fallback. Or, preferred, abandon HF and use the Hetzner deploy. |
| `Invalid string: must match pattern /^[a-zA-Z][_a-zA-Z0-9]*$/` | Hyphens in env-var name | Rename to underscores. |
| `OOMKilled` (exit 137) during `pip install llama-cpp-python` | Source compile peak exceeded sandbox RAM | Use a binary wheel; or move off HF to a host with more RAM. |
| `libc.musl-x86_64.so.1: cannot open shared object file` | abetlen's "linux_x86_64" wheel is built against MUSL | `pip install --no-binary llama-cpp-python` to compile against glibc. |
| `Failed to load model from file` (generic) | Architecture mismatch — llama.cpp doesn't recognise the GGUF's `general.architecture` value | The metadata sniffer in `main.py` will log it. If it's `gemma4`, build llama.cpp from HEAD (current Dockerfile). For other arches, check the supported list at https://github.com/ggml-org/llama.cpp. |
| `apt: not enough free space in /var/cache/apt/archives/` | Disk full on the build host | `docker system prune -af && docker builder prune -af`. If still full, the VPS resize hasn't finalised — power-cycle from the Hetzner panel. |
| `eyes` healthy but backend logs `gemma fallback` | `EYES_API_TOKEN` mismatch between containers, or model loading too slowly | Confirm both containers read the same `EYES_API_TOKEN` from `deploy/.env`. Check `EYES_GEMMA_TIMEOUT_S` (default 60 s). |
| Developer panel doesn't render on Profile page | Email isn't in `ADMIN_EMAILS` and you're not the dev-bypass user | Either click "Continue as dev user" on login, or add your email to `ADMIN_EMAILS` and re-login (the role is reapplied via `apply_admin_role` on every login). |

---

## 10. Outstanding follow-ups (not blocking)

* **Phase 2 vision (mmproj).** The Gemma-4 vision projector hasn't
  been pushed to the model repo yet. When it is, set
  `EYES_MMPROJ_FILE=mmproj-Gemma4E2B-f16.gguf` in `deploy/.env` and
  `docker compose up -d eyes`. The container detects, downloads,
  and passes `--mmproj` to `llama-server` automatically. No code change.
* **Pin llama.cpp to a specific commit** instead of `master` once Gemma 4
  fixes settle upstream (currently `ARG LLAMA_CPP_REF=master` in the
  Dockerfile). Pinning makes builds reproducible across re-deploys.
* **Delete the dead HuggingFace Space** at `Yoram-Jacobs/dressapp-eyes-gguf`
  (the *Space*, not the model repo). The model repo stays — the
  container needs it for downloads.
* **Token leaked in this session must be rotated.** The HF token shown
  in the screenshot during the Variables-UI debugging *should already*
  have been revoked. If not, do it now from
  https://huggingface.co/settings/tokens.

---

## 11. Final state at end of session

* **Hetzner VPS:** CPX32 confirmed (4 vCPU, 7.6 GB RAM, 75 GB disk).
  Eyes container code is staged in this repo but **the new files
  haven't been pushed to GitHub yet**. The user must push from
  Emergent before the VPS's `git pull` will see them. Last command on
  the VPS was `git pull origin main → Already up to date`.
* **Emergent preview pod:** Developer panel is live and verified
  working (screenshotted, toggle round-trip tested). Renders only for
  the `dev@dressapp.io` user since `ADMIN_EMAILS` is empty there.
* **Backend tests:** lint clean (`ruff` + `eslint`), backend serves
  HTTP 200 on `/api/v1/listings?status=active`, `/api/v1/admin/eyes`
  registered in OpenAPI schema and gated behind `require_admin`.

The next concrete action is for the user to push the staged code
changes to GitHub, then run on the VPS:

```bash
cd /srv/AI-Stylist
git pull --ff-only origin main
grep "AS builder" inference-server/eyes/Dockerfile   # gate check
docker system prune -af && docker builder prune -af
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  build --no-cache eyes
docker compose -f deploy/docker-compose.yml --env-file deploy/.env \
  up -d eyes
docker compose -f deploy/docker-compose.yml logs -f eyes
```

Once the log shows `ready: model=phase6-Q4_K_M.gguf vision=False`,
recreate the backend (`up -d --force-recreate backend`), curl the
smoke-test endpoints from inside the backend container, then flip the
Eyes provider to `gemma` from the Profile panel and trigger a real
analyse from the UI to close out Phase O.3.
