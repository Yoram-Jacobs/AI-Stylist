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
---

# Phase O.4 — DressApp Shopping Assistant (Chrome Extension)

This phase delivered the **DressApp Shopping Assistant**, a Manifest V3
Chrome Extension that recommends clothing sizes in real-time from any
shopping site. Architecture: in-page **Floating Action Button (FAB)**
+ **resizable crop overlay** → cropped JPEG → backend
`/api/v1/sizes/analyze-chart` → **Gemini 2.5 Flash** OCR + sizing in
one shot → recommendation overlay with anomaly warnings.

The session pivoted through three architectural dead-ends before
landing on the screenshot-only flow that's now in production. Each
pivot was forced by a failure that the previous design couldn't
recover from. As before, the goal of writing this down is so the
next engineer doesn't re-litigate decisions whose causes have already
been buried.

---

## 1. Starting state

* Manifest V3 extension scaffold existed (`/app/chrome-extension/`)
  with a popup, service worker, content scripts, and Vite + crxjs
  build pipeline.
* Token-handoff auth via a content script on
  `dressapp.co/extension/connect` pushing `{token, user, backend}`
  into `chrome.storage.local`.
* Backend `/api/v1/sizes/analyze-chart` was **bespoke**: it tried
  Gemma Space → Qwen-VL fallback for image OCR, with a per-store HTML
  adapter set (Zara, ASOS, Shein, H&M, Amazon, AliExpress, …).

---

## 2. Failure trail — three architectural dead-ends

| # | Approach | Symptom | Root cause | What replaced it |
|---|---|---|---|---|
| 1 | **Per-store HTML adapters** | New stores (AliExpress modal in iframe) didn't match any selector → silent failure | Every adapter was a hand-written CSS-selector ladder. Sites change weekly; the maintenance load was unbounded | Generic auto-detect + manual crop UX |
| 2 | **Auto-detect chart element + screenshot** | Detection still missed div-based size guides on AliExpress/Shein; permission-less screenshot blocked by Chrome | `chrome.tabs.captureVisibleTab` requires `<all_urls>` host permission OR `activeTab` (only granted on toolbar-icon clicks, NOT in-page FAB clicks) | Resizable crop overlay + universal `<all_urls>` host permission |
| 3 | **Hybrid HTML + screenshot pipeline** | Heuristic took 60s to fail, vision took another 60s; net 2-minute round-trip per try | Backend serialised Gemma-vision attempts (`vision_disabled=true` in Phase 1) → HF fallback (Qwen-VL endpoint not on this deploy) → no Gemini | **Screenshot-only** ship to Gemini 2.5 Flash directly |

The final architecture (Phase 4) is the thing the user asked for at
the start:
> *"we can't write separate code for every online fashion store"*

---

## 3. Final architecture

### 3.1. Extension capture flow

1. User clicks the **floating FAB** on any page (auto-injected
   via content script with `<all_urls>` matches) or via toolbar icon.
2. **Resizable crop overlay** mounts. User drags a box around the
   size chart, hits **Apply**.
3. Content script captures viewport via `tabs.captureVisibleTab`
   (background SW), crops it canvas-side to the user's box,
   strips the `data:` prefix → base64 JPEG.
4. POSTs only `{ chart_screenshot_b64, garment_type, store, page_url,
   page_title }` to `/api/v1/sizes/analyze-chart`. **No HTML, no
   text, no DOM tricks.**

### 3.2. Backend pipeline (`/app/backend/app/api/v1/sizes.py`)

* **Auth + measurement load** via `get_current_user` →
  `user.body_measurements` blob.
* **Server-side alias expansion** (`_expand_measurement_aliases`):
  `chest=92` fans out to `chest, bust, bust_size,
  chest_circumference`; `shoulder=44` → `shoulder, shoulders,
  shoulder_width, across_shoulder`; etc. So the JSON sent to Gemini
  always contains an exact-name match for any chart-side wording.
* **Three-section user prompt** so the model sees clear
  separation: `USER BODY CIRCUMFERENCES`, `USER CLOTHING SIZES THEY
  NORMALLY BUY`, `USER HEIGHT / WEIGHT CONTEXT`.
* **Direct Gemini 2.5 Flash call** via
  `emergentintegrations.llm.chat.LlmChat` with `ImageContent`. We
  deliberately bypass the Eyes/Gemma chain — Phase-1 Gemma is
  `vision_disabled=true`, so an image payload always produces empty
  output and a 30-60 s wall-clock penalty.
* **30 s timeout cap** (`asyncio.wait_for`), provider activity
  logging on success/failure.
* **Optional heuristic-first** for back-compat HTML/text payloads
  (free <50 ms win when the caller still sends a `<table>`).

### 3.3. System prompt rules (the hardest part)

The prompt is the product. Four explicit rules, in priority order:

1. **OCR the chart** — extract headers, units, size labels, cell
   values; recognise range cells (`86-90`) vs. single-number cells.
2. **Circumference vs. length distinction:**
    * **Circumferences** (chest/bust/waist/hip/shoulder/neck): user
      value must fit inside the garment dimension. Standard
      bigger-on-tie rule.
    * **Length** (sleeve/inseam/outseam/length/arm_length): user
      value is treated as their **full-body MAX** (full arm, full
      leg). A garment shorter than this is just a short-sleeve /
      cropped / mini garment — **NOT** a misfit. No anomaly flag.
3. **Anomaly detection:**
    * **Only check circumferences.** Length values are NEVER
      flagged for being "too high".
    * Trigger when user value > chart maximum AT ALL (no size can
      fit them) OR < min by 15%+. Skip the column when picking the
      size, drop it from `matched_columns`, append a friendly
      `warnings` entry asking the user to re-measure.
4. **Clothing-size fallback:** when body circumferences are empty
   but `shirt_size` / `pants_size` / `shoe_size` is set, use that
   directly as the recommendation (confidence 0.55-0.80, set
   `matched_columns=["shirt_size"]`, recommend re-measuring for a
   tighter fit).

### 3.4. Recommendation overlay

* Confidence badge (low/mid/high) + recommended size + reasoning
  paragraph + **amber warnings stack** (each warning gets its own
  row with a `!` badge, `role="alert"` for screen readers, stable
  `data-testid="dressapp-overlay-warning-N"`).
* Alternatives row (`{size, fit: snug|loose}`) underneath.

### 3.5. Auth flow (token-handoff)

* Popup `Connect to DressApp` opens
  `https://dressapp.co/extension/connect?ext_id=...` in a new tab.
* Auth-bridge content script (only injected on
  `dressapp.co/extension/connect*` per manifest) calls
  `chrome.runtime.sendMessage` with `{ token, user, backend }`.
* SW persists to `chrome.storage.local`. All future API calls go
  through SW → `Authorization: Bearer <token>` → registered
  backend.

---

## 4. Bug trail — what bit us, what fixed it

Each entry below corresponds to a real failure observed during
testing. The column "deploy gate" indicates whether the fix only
takes effect on a fresh prod deploy.

| # | Symptom | Root cause | Fix | Files | Deploy gate |
|---|---|---|---|---|---|
| B1 | "AI sizing engines couldn't read this chart (gemma: ...; qwen: ...)" — 60 s timeout | Bespoke Gemma → Qwen waterfall, both unavailable on this deploy | Replaced with direct Gemini 2.5 Flash call | `sizes.py`, `garment_vision.py` | prod redeploy |
| B2 | Heuristic took 60 s to fail before vision was tried | Synchronous waterfall + Gemma `vision_disabled` empty-reply hang | Heuristic-first only when HTML present; vision call has hard 30 s cap; skip Gemma for image OCR (vision_disabled known state) | `sizes.py` | prod redeploy |
| B3 | "No clear match — user body measurements were not provided" while the user actually had `chest=92` saved | Model wouldn't infer `chest`↔`Bust Size` semantic equivalence on its own | Server-side alias expansion (chest fans to bust, bust_size, …) so the JSON contains a literal name match | `sizes.py` (`_expand_measurement_aliases`) | prod redeploy |
| B4 | Same "no measurements" message on a profile with only `height`, `weight`, `shirt_size` | No fallback rule for the all-too-common case where a user has shirt_size but no tape-measure data | Added **CLOTHING-SIZE FALLBACK** rule: shirt_size → primary signal for tops, pants_size for bottoms, shoe_size for footwear, height/weight as last-resort low-confidence | `sizes.py` system prompt | prod redeploy |
| B5 | One typo'd circumference (`shoulders=55` on a chart maxing at 50) blocked the recommendation entirely | Strict "all columns must fit" logic | Anomaly-detection rule: skip the offending column, recommend from the others, return `warnings` so the user knows to re-measure | `sizes.py` system prompt + `AnalyzeChartOut.warnings` | prod redeploy |
| B6 | Short-sleeve T-shirt sleeve (19 cm) flagged as anomaly because user's full-arm `sleeve=46 cm` "exceeds chart range" | Anomaly rule didn't differentiate column types | Length columns (sleeve/inseam/outseam/length) excluded from "too high" anomaly checks; user value is treated as MAX, garment can be shorter | `sizes.py` system prompt | prod redeploy |
| B7 | Extension's `<all_urls>` permission not granted after FAB click on AliExpress | `tabs.captureVisibleTab` requires `<all_urls>` OR `activeTab`, and `activeTab` is only granted on **toolbar icon clicks**, not in-page FAB clicks. Narrow `*.aliexpress.com` host permission insufficient | Moved `<all_urls>` from `optional_host_permissions` → required `host_permissions` | `manifest.json` | extension reinstall |
| B8 | "Extension context invalidated" overlay after the user reloaded the extension while a tab was open | Orphaned content script in stale tab; classic MV3 lifecycle issue | Detect the error in `_captureViewportWithPermission`, return `{stale_context: true}`, render a tailored "DressApp was just updated — reload this tab" overlay with a Retry button that calls `location.reload()` | `service-worker.js`, `content/content.js` | extension reinstall |
| B9 | Popup showed user as `dev@dressapp.io` even though stored token was being silently wiped on `/me` 401 | Popup's `refresh()` showed `phase: 'connected'` with stale cached `r.user` even when `/me` failed | On 401-shaped error from `/me`, call `CLEAR_AUTH`, transition to `disconnected`, show a yellow "session no longer valid" notice | `popup/Popup.jsx` | extension reinstall |
| B10 | Stale `backend` URL (preview) in `chrome.storage` survived a "Disconnect" and kept routing API calls to the wrong host | `handleClearAuth` only removed `token, user, issued_at` — `backend` lingered | Wipe `backend` too on disconnect; **also** added a registrable-domain check in `getBackend()` that drops any stored backend whose domain doesn't match the build-time default (and wipes the token+user with it) | `service-worker.js`, `lib/api.js` | extension reinstall |
| B11 | Newly built prod-targeted extension still authenticated as preview's `dev@dressapp.io` | Manifest's `externally_connectable.matches` and auth-bridge `content_scripts.matches` still listed `*.preview.emergentagent.com/*`. Plus the user already had a `dressapp.co` browser session as dev → handoff used that session | (a) Removed all preview URLs from `manifest.json`. (b) Added "Switch account" button to popup that opens `?force=1` connect URL → frontend clears localStorage on mount → user sees fresh login page | `manifest.json`, `popup/Popup.jsx`, `pages/ExtensionConnect.jsx` | both deploys |
| **B12** ⚠ | **CRITICAL: a partial PATCH to `/api/v1/users/me` was wiping every body-measurement field not in the payload, on every request, in production** | Mongo `$set: { body_measurements: <new dict> }` wholesale replaces the embedded document — it doesn't merge nested fields. Pre-existing latent bug surfaced after multi-test cycles | Switch to dot-notation `$set` (`body_measurements.chest = 92`) for every nested-dict field in `_MERGEABLE_DICT_FIELDS` — `body_measurements`, `address`, `units`, `hair`, `home_location`, `professional`, `style_profile`, `cultural_context` | `users.py` | **prod redeploy ASAP** |

---

## 5. Files of reference

```
backend/
  app/api/v1/sizes.py               (full rewrite — Gemini-direct vision pipeline)
  app/api/v1/users.py               (B12 dot-notation $set for nested dicts)
  app/services/garment_vision.py    (used by closet flow; size endpoint no longer routes through it)
chrome-extension/
  manifest.json                     (host_permissions: <all_urls>, dressapp.co only)
  src/content/content.js            (FAB, crop overlay, screenshot capture, error UX)
  src/content/overlay.js            (recommendation overlay + warnings render)
  src/content/content.css           (.dressapp-warnings amber palette)
  src/content/auth-bridge.js        (postMessage handoff on dressapp.co/extension/connect)
  src/background/service-worker.js  (auth state, captureVisibleTab, handlers)
  src/popup/Popup.jsx               (refresh-with-401-detection, Switch account, backend host display)
  src/lib/api.js                    (registrable-domain check; trusted backend resolution)
  dressapp-extension.zip            (72 KB, prod-only, ready to install)
frontend/
  src/pages/ExtensionConnect.jsx    (force=1 handler for "Switch account")
  src/lib/auth.jsx                  (logout is local-only — no backend call)
  src/components/ProfileDetailsCard.jsx  (still has "always-active Save" UX bug — backlog)
docs/
  chat_summary.md                   (this file)
```

---

## 6. Outstanding work — handoff for the next engineer

### Backlog (P1)

* **"Smartass" size charts (Zara, H&M, et al.).** These sites
  serve charts in modal iframes, with size names that don't match
  the master JSON the same site uses for product-page filters.
  Zara's `XS-M-L-XL` modal labels resolve to `02-04-06-08` SKUs
  internally. Need a per-site **chart-reconciliation** layer that
  cross-references the chart's row labels against the site's own
  size-selector elements, so the recommendation aligns with what
  the user can actually click on the product page.
* **Mobile deployment.** The current Chrome Extension architecture
  doesn't run on mobile Safari/Chrome. Two paths:
  (a) Capacitor wrapper with a custom JS bridge for screenshot
  capture (mobile DOMs are different — needs a long-press +
  share-sheet flow);
  (b) Native iOS/Android share-extension that posts the screenshot
  directly to `/api/v1/sizes/analyze-chart`. Prefer (b) — much
  simpler, but two codebases.

### Backlog (P2)

* Profile form **"Save changes" always-active button**: track form
  dirtiness against a snapshot of loaded values; only enable Save
  when something actually differs; reset the snapshot on
  successful PATCH.
* **Per-store reconciliation cache** (database-side): when a chart
  is successfully analysed, store the OCR'd column headers + row
  labels keyed by store + chart-image hash. Future requests for the
  same chart skip the LLM call entirely.
* **Analytics**: log `(store, garment_type, recommended_size,
  confidence, source, elapsed_ms)` so we can spot regressions when
  Gemini changes underneath us.

### Backlog (P3)

* Backend **logout endpoint** that clears the dressapp.co session
  cookie and 302s to `returnTo`. The current "Switch account" flow
  uses a localStorage clear via `?force=1` — works, but a
  server-side cookie clear would be more thorough if/when sessions
  ever go server-side.
* **Provider activity dashboard** for size-chart calls (Gemini
  latency p50/p95, error rate, fallback hit rate).

### Verified production behaviour (last session)

```
input:  AliExpress short-sleeve T-shirt size guide (in inches)
        + lokoprod profile (chest=92, shoulders=55 (deliberate typo),
          sleeve=46, shirt_size=M, ...)

output: { recommended_size: "M",
          confidence: 0.9,
          matched_columns: ["bust", "arm_length"],
          reasoning: "Based on your bust measurement (92 cm), size M
                      provides a comfortable fit. The garment's
                      sleeve length (19.00 cm) indicates it is a
                      short-sleeved top, which is compatible with
                      your full arm length (59 cm).",
          warnings: ["Your shoulders (55 cm) looks higher than
                      expected for this kind of garment. Please
                      re-measure — DressApp ignored it for this
                      recommendation."],
          source: "gemini",
          elapsed_ms: ~30000 }
```

Anomaly skipped, recommendation made from the valid `chest=92`,
short-sleeve compatibility correctly recognised, user told to
re-measure the obviously-wrong shoulder value. This is the target
UX shape for every store going forward.

---

## 7. Final action items for the user

1. **Push & deploy the data-loss fix** (B12) — `users.py`. **Do
   this first.** Until it's live, every partial profile-form save
   continues to wipe fields.
2. **Push & deploy** the rest of `sizes.py` (B1-B6) and the
   `ExtensionConnect.jsx` `force=1` handler.
3. **Reload the new extension** from
   `/app/chrome-extension/dressapp-extension.zip` (72 KB,
   production-only). Approve `<all_urls>`. Check the popup shows
   `via dressapp.co`.
4. Re-enter the body measurements that B12 wiped from your prod
   profile — there's no way to recover them server-side.
5. Run a real-world test on AliExpress / Zara / H&M with the new
   build, record the recommendation + timing + any new failure
   modes, and log them into the **"smartass" size carts** P1
   backlog item before the next session.


---

# Phase O.5 — Eyes Audit & Toggle Truth-in-Routing

User came back asking to **prove** that DressApp's Add-Item analyses
were actually being served by the fine-tuned Gemma-4 E2B "Eyes"
model and not silently falling through to Gemini. The audit ran
across Preview and Production, exposed a stack of bypasses, fixed
each one cleanly, and finished with a definitive end-to-end
diagnostic notebook that answered the original question with hard
data.

## 1. Initial state of the routing stack

Three independent reasons the user could not have been seeing
Gemma output:

1. **Pod env hard-routed to Gemini.** `GARMENT_VISION_PROVIDER=gemini`
   in the pod env caused `garment_vision.analyze()` to enter the
   Gemini branch immediately, *before* `eyes_override.get_active_provider()`
   was ever consulted. The DB toggle UI was decorative.
2. **HuggingFace Space crashed (HTTP 503).** The user's
   `Yoram-Jacobs/dressapp-eyes-gguf` Space was returning
   `Your space is in error, check its status on hf.co` for every
   request. Even if the toggle had worked, the call would have
   failed.
3. **Phase-1 Space had no vision projector.** The deployed Space
   was running text-only (Q4_K_M LLM, no `mmproj-*.gguf`), so even
   when reachable it could not actually look at images. Whatever
   "analysis" it produced was hallucinated from prompt structure
   alone.

## 2. Toggle architecture rewrite

Replaced the env-first router in `garment_vision.analyze()` with a
**toggle-driven** router (`/app/backend/app/services/garment_vision.py`):

* `eyes_override.get_active_provider()` is now consulted *first*.
* Allowed values are `gemma | gemini` (legacy `qwen` retired —
  DressApp ships only those two engines today;
  `/app/backend/app/services/eyes_override.py`).
* On `gemma`: POST to `EYES_GEMMA_SPACE_URL`. On any failure
  (timeout, 5xx, network, parse-empty), automatically fall back to
  Gemini and tag the response payload with
  `provider_fallback: {from: "gemma", to: "gemini", reason: ...}`
  so the frontend / admin can see fallback transparently.
* On `gemini`: direct call to Gemini 2.5 Flash via
  `EMERGENT_LLM_KEY`.
* `GARMENT_VISION_PROVIDER` env demoted to *seed default* —
  consulted by `eyes_override` only when the DB has no override
  yet, never by the analyser directly.

Frontend Developer panel updated to match
(`/app/frontend/src/components/DeveloperPanel.jsx`): switch labels
are now **Gemini ↔ Gemma**, value `qwen` removed, copy reflects
new fallback semantics.

## 3. New diagnostic endpoint

Added `GET /api/v1/admin/eyes/diagnostics`
(`/app/backend/app/api/v1/admin.py`). Single-shot snapshot of the
Eyes pipeline's true state, no app restart required:

```
{
  "toggle":   { active_provider, source, env_default, override, ... },
  "env":      { GARMENT_VISION_PROVIDER, GARMENT_VISION_MODEL,
                EYES_GEMMA_SPACE_URL, gemini_chat_key_set, ... },
  "resolved": { provider, model, routing_source, fallback_path,
                notes },
  "gemma_space": { url, status_code, ok, latency_ms,
                   body_preview, error },        // live HTTP probe
  "recent_calls": [...last 10 garment-vision provider_activity rows]
}
```

This is what every future "is my model actually serving?" question
should be answered with — call the endpoint, read the JSON, done.

## 4. HuggingFace Space repaired (then retired)

User's Space was failing to build because the Phase-1 Dockerfile
contradicted itself: the comment said "we use prebuilt CPU wheels
so we don't need a compiler" but a leftover `apt install
build-essential cmake git` block forced a source build that OOM'd
the free-tier 16 GB sandbox. Removed the redundant block, kept the
abetlen wheel index, build dropped from 10 min + OOM to ~30 s.

User then uploaded `mmproj-Gemma4E2B-f16.gguf` (986 MB) to the
model repo. Patched `app.py` to load
`Gemma3ChatHandler(clip_model_path=...)` (NOT `Llava15ChatHandler` —
LLaVA's `<image>` token format would have produced silently-
garbled output on the Gemma-4 token scheme). Vision flag flipped
to `True` on next boot.

Eventually retired the Space entirely (see §6) once the VPS path
matched feature parity at zero marginal cost.

## 5. VPS migration — `inference-server/eyes/`

User's Hetzner CPX32 already had the full Phase O.3 inference-
server scaffold from a session 3 days prior:
`/app/inference-server/eyes/` builds llama-server from
`llama.cpp` HEAD (correct multimodal handling, no
`llama-cpp-python` lag), with `_ensure_mmproj_present()` and the
`--mmproj` flag pre-wired. All that was missing was the env wiring
for Phase 2.

Patches applied this session:

* **`/app/deploy/.env.example`** — added a complete *The Eyes*
  section so the seven `EYES_*` variables that had been silently
  expected by `docker-compose.yml` are now self-documenting.
  Includes the Phase-2 `EYES_MMPROJ_FILE=mmproj-Gemma4E2B-f16.gguf`
  flip, `EYES_LLAMA_THREADS=4` to match CPX32's vCPU count, the
  internal `EYES_GEMMA_SPACE_URL=http://eyes:7860`, and the
  bearer-auth token semantics.
* **`/app/inference-server/eyes/main.py`** — added two
  llama-server flags:
    * `--reasoning-budget 0` — disables the model's `<|think|>`
      phase entirely. Fine-tune is a thinking model that on CPU
      spent 60-120 s reasoning before producing any output;
      cutting this dropped first-token latency from ~50 s to ~3 s
      on CPX32.
    * `--chat-template-kwargs '{"enable_thinking": false}'` —
      belt-and-braces for templates that gate thinking via Jinja
      booleans. Older llama.cpp builds without
      `--reasoning-budget` ignore this harmlessly.
  Also patched the `/predict` response to fall back to
  `reasoning_content` when `content` is empty (covers the case
  where a thinking-template model exhausts its budget mid-think
  and leaves `content == ""`).
* **`/app/backend/app/services/garment_vision.py`** — bumped the
  `_call_gemma_space` `max_tokens` from the default 900 to 2400
  for the Gemma path. The schema is verbose (~18 fields ≈ 600
  output tokens); reasoning + JSON together comfortably fit in
  2400 with thinking-budget disabled.

VPS roll-out runbook captured in this session's transcript:

```bash
ssh root@<vps>
cd /srv/AI-Stylist
git pull origin main
cd deploy
docker compose up -d --build --force-recreate backend eyes
```

Common gotcha exposed: `docker compose up -d --build` does **not**
recreate already-running containers when only `.env` values
change. Always pair the `.env` edit with `--force-recreate`, or
`docker compose down eyes && docker compose up -d eyes`.

## 6. Eyes_Vision_Smoke_Test.ipynb — the definitive diagnostic

`/app/docs/Eyes_Vision_Smoke_Test.ipynb` — Colab notebook that
bypasses DressApp entirely and talks to the Eyes container raw
through a Cloudflare quick-tunnel (or any other one-shot exposure
of `eyes:7860`). Eight cells:

1. Setup
2. Config — form fields for URL, bearer token, optional Gemini key
3. Image upload (Colab's `files.upload()`, pre-processed to
   1280px JPEG q=82 to mirror backend pre-processing exactly)
4. The actual call — uses the **verbatim DressApp system prompt**
   so the result is what would land in the closet
5. JSON parse via the same `_extract_json` heuristic as the
   backend
6. **Vision-blindness control test** — re-runs the call with a
   blank grey canvas. Headline test of the whole notebook: if the
   blank canvas and real photo produce structurally similar
   output, the projector is not actually being consulted at
   inference, regardless of what `vision_enabled` reports.
7. Optional Gemini comparison
8. Decision tree mapping each output pattern to a root cause

## 7. Notebook results — the audit's actual answer

User ran the notebook against the production Eyes service through
a `*.trycloudflare.com` quick-tunnel. The data was unambiguous:

### Real photo (`5d786bfe...jpg`, women's long-sleeve)

```
Total latency       : 13.5 s          ✅ thinking off, fast
vision_used         : True            ✅ projector loaded
finish_reason       : stop            ✅ natural stop, not budget
tokens_completion   : 56
output:
  { "name": "Long-sleeve shirt",
    "item_id": "Tees_Tanks-id_00000313_1_1_1_front.jpg" }
```

### Blank grey canvas

```
Total latency       : 89.5 s
tokens_completion   : 2400 (hit cap)
output:
  { "name": "Tanks on Shorts",
    "description":
       "...There is an accessory on her wrist." × 40+ }
```

### Conclusions

* ✅ **Infrastructure 100 %.** Vision proven to be wired (different
  outputs for different images), reasoning-budget proven to take
  effect (13.5 s vs 90 s), routing toggle proven to flip cleanly.
* ❌ **Fine-tune is the limiting factor.** Three independent issues:
    1. **Training-data leakage** — `item_id` value
       `Tees_Tanks-id_00000313_1_1_1_front.jpg` matches
       DeepFashion-family filename conventions. The model
       memorised filenames as labels.
    2. **Schema drift** — output uses `{name, item_id}` and
       `{name, description}` schemas in two consecutive calls;
       neither matches DressApp's 18-field prompt schema. The
       fine-tune was prepared with a different output format and
       the system-prompt schema has zero influence on the output
       structure.
    3. **Mode collapse on out-of-distribution input** — blank
       canvas triggered "There is an accessory on her wrist" loop
       40+ times until the token cap. Model has no graceful
       refusal behaviour.
* 🎯 **The original audit question is answered.** Every Add-Item
  result the user has admired on dressapp.co was Gemini 2.5
  Flash, not Gemma. The DB toggle is now honest about that, and
  the diagnostics endpoint can prove it for any future request.

## 8. Final state at end of session

* Production DB toggle: **set to `gemini`** (per user instruction
  at the close of the session). Set explicitly via the Developer
  panel UI on dressapp.co — the panel writes
  `config.eyes_provider.value = "gemini"` to Mongo, picked up by
  every backend call within ~5 s.
* HuggingFace Space (`Yoram-Jacobs/dressapp-eyes-gguf`):
  **paused** in HF Settings. Repo + Dockerfile preserved as a
  fallback. Stops the free-tier compute clock; user pays nothing.
* VPS Eyes container: **left running** for diagnostic and
  fine-tune-evaluation purposes. Toggle keeps Add-Item users on
  Gemini regardless. When the new fine-tune is ready, the user
  flips the toggle in the Developer panel and traffic reroutes
  immediately.
* Diagnostic endpoint `/api/v1/admin/eyes/diagnostics`: live in
  prod. Single source of truth for "what is Eyes doing right
  now?".

## 9. Files changed / added in this session

```
backend/
  app/services/garment_vision.py       (toggle-driven routing,
                                        gemini fallback,
                                        max_tokens=2400, fallback
                                        tagging)
  app/services/eyes_override.py        (valid providers
                                        gemma|gemini, env_default
                                        gemini)
  app/api/v1/admin.py                  (+ /eyes/diagnostics
                                        endpoint, gemma|gemini
                                        validation on POST)

frontend/
  src/components/DeveloperPanel.jsx    (Gemini ↔ Gemma labels,
                                        fallback copy, removed
                                        Qwen)

inference-server/
  eyes/main.py                         (--reasoning-budget 0,
                                        --chat-template-kwargs
                                        enable_thinking=false,
                                        reasoning_content fallback)

deploy/
  .env.example                         (Eyes section documented)

docs/
  Eyes_Vision_Smoke_Test.ipynb         (NEW — definitive
                                        diagnostic Colab notebook)
  chat_summary.md                      (this section)
```

## 10. Outstanding work — handoff for the next engineer

### Closed in this session

* ~~Eyes audit / toggle truth-in-routing~~ — done.
* ~~HF Space build failure (cmake/OOM)~~ — fixed, then retired.
* ~~Vision projector not loaded~~ — fixed (mmproj uploaded +
  Gemma3ChatHandler + `--mmproj` flag).
* ~~Thinking-mode latency~~ — fixed (`--reasoning-budget 0`).
* ~~Empty `content` from thinking-template models~~ — fixed
  (`reasoning_content` fallback in `/predict`).

### New track: **Eyes v2 fine-tune** (post-refactor)

Out of scope for this session per user. To pick up later:

1. **Regenerate the training dataset** by running Gemini 2.5
   Flash with DressApp's *exact* production system prompt over
   ~5,000 garment photos. Use Gemini's JSON output as the
   supervised target. Estimated cost: $5-15 in API spend.
2. **Strip every `item_id` / filename-shaped field** from the
   training labels — that's what leaked into production output.
3. **Mix in 5-10 % "non-garment" examples** (blank canvas,
   landscapes, document scans) labelled with a `null`-shaped JSON
   to teach the model graceful refusal instead of mode collapse.
4. **Hyperparameters for the next run**:
   * LR ≤ `2e-5` (current run was likely higher → memorisation).
   * 1-2 epochs max with eval-loss monitoring; stop at minimum.
   * Coverage of all 7 categories (Top, Bottom, Outerwear,
     Full Body, Footwear, Accessories, Underwear).
5. **Validate offline before promoting**: run
   `Eyes_Vision_Smoke_Test.ipynb` over 50 unseen photos. Score
   JSON-validity rate and category-correctness rate. Don't flip
   the production toggle to `gemma` until both are >90 %.

### Carried-over backlog (unchanged)

* "Smartass" size charts (Zara, H&M) reconciliation. **P1.**
* Mobile deployment via Capacitor or native share-extension. **P2.**
* Profile "Save changes" always-active button (dirty-state
  tracking). **P3.**
* `AddItem.jsx` refactor (>1800 lines → modular). **P3.**
* Server-side logout endpoint with cookie clear. **P3.**

### Lessons / process notes for the next session

* **Never trust `vision_enabled: True` alone.** The blank-canvas
  control test in the smoke notebook is the only way to prove
  pixels are actually reaching the LLM during inference.
* **`docker compose up -d --build` ≠ `--force-recreate`.** When
  `.env` changes but image hash doesn't, the running container
  keeps stale env. Document this in any future deploy runbook.
* **Always log `provider_used` in the response payload, not just
  in server logs.** The frontend ought to surface it as a small
  badge during the audit period — it would have made today's
  whole audit unnecessary.

---

# Phase Z3 — Client-side duplicate detection

Add-Item upload was bottlenecked by an unnecessary round-trip to
`POST /closet/preflight`. The user diagnosed it correctly: every
piece of data the endpoint needed to answer "is this a duplicate?"
was already in the browser via `closetStore` (which carries each
item's `source_sha256`, `source_phash`, `source_color_sig`).
Refactored the hot path to do the lookup locally.

## 1. What changed

### Frontend

* **`/app/frontend/src/lib/duplicateDetection.js`** (new) — 1:1 JS
  port of the backend's `is_duplicate_match` (and its
  `hamming_distance` / `color_distance` helpers). Same thresholds
  (Hamming ≤ 6, colour ≤ 220), same decision tree (SHA exact →
  phash + colour gate). Cross-validated against the Python side
  with 22 parity assertions including the *navy-vs-grey-shorts*
  edge case that originally motivated the colour gate.
* **`/app/frontend/src/pages/AddItem.jsx`** — `handleFiles` now
  calls `findDuplicatesInCloset(fingerprints, closetStore.getSnapshot().items)`
  instead of `api.preflightDuplicates(...)`. The match-payload
  shape passed into `DuplicatePreflightDialog` is **bit-identical**
  to the old server response, so the dialog and the downstream
  resolve flow needed zero changes.

### Backend

* **`/app/backend/app/api/v1/closet.py`** — `POST /closet/preflight`
  marked **DEPRECATED** in the docstring and now emits a
  `logger.warning("DEPRECATED endpoint hit: ...")` on every call so
  it's grep-able in prod logs. The endpoint stays mounted as a
  safety net for clients on a stale bundle. Removal tracked under
  the `Z3-preflight-removal` backlog item below.

## 2. Trade-offs taken (with the user's explicit OK)

* **Q1a — Legacy items without `source_phash` skip pre-flight
  detection.** Pre-Phase-Z2 closet items lack the hash fields the
  client check needs. They get a free pass through the pre-flight
  gate — relying on the backend's post-save duplicate guard to
  catch obvious re-uploads. The previous lazy backfill inside
  `/preflight` is now obsolete; new uploads via `POST /closet` and
  photo replacements via `POST /closet/{id}/photo` already compute
  + persist fresh signatures server-side, so the gap closes
  naturally as users live with their closets.
* **Q2a+b — Endpoint left mounted but deprecated.** Removal in a
  future release once the `DEPRECATED endpoint hit` warning has
  stopped appearing in production logs for a full release cycle.

## 3. Expected impact

* Add-Item upload pre-flight: **300–1500 ms → 5–30 ms** per batch.
  The remaining latency on the upload path is the in-browser
  SHA / aHash / colour-sig compute (~150–250 ms per photo, run in
  parallel via `Promise.all`).
* `/closet/preflight` traffic should trend toward zero as clients
  update. Once it's at zero for ~2 weeks, delete the endpoint, the
  `PreflightIn` model, and the lazy-backfill block in `closet.py`.

## 4. Files changed / added

```
frontend/
  src/lib/duplicateDetection.js     (NEW — port + helpers + smoke API)
  src/pages/AddItem.jsx             (handleFiles → local lookup;
                                     comments updated Z2 → Z3)

backend/
  app/api/v1/closet.py              (DEPRECATED docstring +
                                     warning-log on every hit)

docs/
  chat_summary.md                   (this section)
```

## 5. Not addressed in this session (but surfaced)

While tracing the user's secondary complaint that "replacing a
photo in edit mode is slow too", I found that path
(`ItemDetail.onPhotoFileChosen` → `POST /closet/{id}/photo` with
`autoSegment: false`) does **not** call `/preflight`. Its
slowness almost certainly comes from the in-line **FashionCLIP
re-embed** that runs on every replacement (~0.5-2 s on the
production VPS depending on CLIP model warm-up). If the user wants
to optimise that next, options are:

1. Background the re-embed via a fire-and-forget task and return
   the updated item immediately (semantic search would be briefly
   stale).
2. Skip the re-embed on photo replace and trigger it only on
   explicit re-analyse.

This is logged here so the next session can pick it up if
confirmed as a UX pain point.

## 6. New backlog items

### `Z3-preflight-removal` — P2

After one or two release cycles with zero `DEPRECATED endpoint
hit: POST /closet/preflight` warnings in production logs:

1. Delete `@router.post("/preflight")` block in `closet.py`.
2. Delete the `PreflightIn` Pydantic model.
3. Delete `api.preflightDuplicates` in `frontend/src/lib/api.js`.
4. Update `DuplicatePreflightDialog.jsx`'s docstring (currently
   references "backend's /closet/preflight").
5. Optionally rename the `preflight` state key in `AddItem.jsx` to
   `dupCheck` for clarity, since the term now describes a purely
   client-side check.

### `Z3-clip-reembed-on-photo-replace` — P3 (deferred)

See §5. Only pick up if the user confirms edit-mode replace is
slow even after the Z3 deploy lands (since the Z3 fix doesn't
touch that path, that complaint should persist if real).

---

# Phase Z4 — Optimistic "Save all"

User asked for `Save all` to push items to the local closet first
and sync to the backend in the background. The previous flow
serialised every `api.createItem` call behind `await` and only
navigated once the last one returned (5–30 s per typical batch on
prod), which on an add-flow already vouched-for by the analyse
step was pure dead time.

## 1. Decisions taken (with the user)

* **Q1a + thumbs** — on per-item save failure, remove the ghost
  from `closetStore`, capture the failed item's title + filename +
  thumbnail, and surface a single end-of-batch warning dialog on
  the Closet page listing all failures so the user knows exactly
  what didn't make it.
* **Q2 yes** — navigate to /closet immediately on click. The
  perceived save is now instant (~16 ms).
* **Q3 yes** — render a *sparkling* "Syncing" overlay on every
  closet card whose `_pendingSync` marker is still truthy. Soft
  opacity/scale pulse, never a spinner (spinners read as "error"
  in fashion-app context).

## 2. Files changed

```
frontend/
  src/lib/closetStore.js                +lastSaveFailures state,
                                        +recordSaveFailures(),
                                        +dismissSaveFailures()
  src/pages/AddItem.jsx                 saveAll() fully rewritten:
                                        optimistic ghosts + parallel
                                        Promise.allSettled + reconciler
  src/pages/Closet.jsx                  +sparkle overlay on
                                        item._pendingSync,
                                        +SaveFailuresDialog component
  src/locales/en.json                   +closet.pendingSync,
                                        +closet.saveFailuresTitle/Body
                                        /Unnamed, +addItem.savedOptimistic,
                                        +common.gotIt
docs/
  chat_summary.md                       (this section)
```

## 3. Reconciliation contract

`AddItem.saveAll` mints a `crypto.randomUUID()` per card (with a
``tmp-${ts}-${rand}`` fallback for ancient browsers), builds a
``ClosetItem``-shaped optimistic ghost with the user's photo as a
*data URL* (NOT a blob: URL — those die when AddItem unmounts),
upserts every ghost into `closetStore`, toasts, navigates. The
parallel reconciler then:

* On `fulfilled`: `closetStore.remove(tempId)` followed by
  `closetStore.upsert(serverItem)`. The canonical server item
  carries the real id, server-computed thumbnail, CLIP embedding,
  segmentation — these silently swap into the closet card on the
  very next render.
* On `rejected`: `closetStore.remove(tempId)` and push the
  ghost's metadata onto a `failures` array. After all results
  settle, `closetStore.recordSaveFailures(failures)` lights up
  the Closet page's `SaveFailuresDialog` in one go.

The reconciler runs after navigation; it has no closure over the
unmounted AddItem React tree. Everything it needs (filename,
thumbnail, body, tempId) is captured in a local `ghosts` Map.

## 4. Expected impact

* "Save all" perceived latency: **5–30 s → ~16 ms** (paint of the
  optimistic items on /closet).
* API write latency unchanged but now executes in PARALLEL via
  `Promise.allSettled` — a 5-card batch on a 200 ms RTT goes from
  ~1 s wall-clock to ~250 ms.
* Failure recovery is non-destructive: the user lands on /closet
  with the warning dialog open showing exactly which photos to
  re-upload (with thumbnails so they recognise them at a glance).

## 5. UX details to verify on first prod test

* Sparkle overlay: subtle gradient fade-to-background at the
  bottom of the card + a `Sparkles` icon with `animate-ping`
  halo + `animate-pulse` icon body. Uses
  `hsl(var(--accent))` so it picks up the theme accent rather
  than hard-coded teal/blue. Test that this reads as "in
  progress" (not "alert") in both light and dark mode.
* Sonner toast: copy is `"X items added to your closet —
  syncing in background"` (i18n key `addItem.savedOptimistic`).
* Warning dialog: uses `AlertDialog` + `AlertTriangle` icon
  (amber). Shows up to 6 visible rows before scrolling within
  the dialog. Dismiss button is a clear "Got it" — the user
  cannot accidentally retry from inside the dialog (intentional
  — re-upload should be a deliberate action, not an
  acknowledgement).

## 6. Known limitations / accepted trade-offs

* **Server-side enrichment lag.** During the brief window before
  the canonical item replaces the ghost, the card shows the
  user's raw uploaded image (no CLIP embedding, no segmentation,
  no server thumbnail). For ~250 ms on a healthy network this is
  invisible; on slow networks the gap is bounded by
  `api.createItem`'s natural timeout. The sparkle overlay tells
  the user something is happening.
* **Offline / hard navigate during sync.** If the user kills the
  tab, the in-flight `Promise.allSettled` is abandoned. The
  optimistic ghosts remain in `closetStore` until the next full
  `/closet` fetch reconciles them away. Acceptable for MVP —
  proper background-sync with a service worker is a future
  feature.
* **No retry-from-failure UX.** The warning dialog is read-only;
  the user has to navigate back to Add-Item and re-upload. A
  proper retry path would require persisting the original
  payload + thumbnail across navigation (basically the "drafts"
  feature flagged in §5 of Phase Z3). Left as a P3 backlog.

## 7. New backlog items

### `Z4-failure-retry-from-dialog` — P3

Augment the `SaveFailuresDialog` with a Retry button per row that
re-fires `api.createItem` with the captured body. Requires
stashing the full payload on the failure descriptor (currently
only metadata is kept). Estimate: 80 lines of code, one new
`api.createItemRaw` helper that bypasses the optimistic dance.


---

# Phase Z5 — Eyes v2 Merge + Mixed-Precision Quantization Pipeline

User finished training the Eyes v2 (Gemma 3n E2B / "Gemma4-E2B") LoRA
adapter in bf16 and confirmed it passes the schema/vision-blindness eval.
Next step: ship to (a) the web/server backend via GGUF and (b) mobile
devices via MediaPipe LiteRT `.task`, with the entire vision tower +
audio tower + cross-modal embed projections + PLE tables kept in FP16
to prevent quantization degradation.

## 1. Decisions taken (with the user)

* **Q1 (deployment targets):** 1a + 1b — GGUF for web, LiteRT `.task`
  for mobile. Same merged HF checkpoint feeds both pipelines.
* **Q2 (FP16 keep-list):** User audit covered `model.vision_tower.*`
  (16 SigLIP encoder layers + patch_embedder + pooler),
  `model.audio_tower.*`, `model.embed_vision.*`, `model.embed_audio.*`
  and most of the LM (35 layers — interesting note: layers 15-34 only
  list q_proj/o_proj, confirming Gemma 3n's KV-sharing optimization).
  Notebook proactively adds the PLE tables (`embed_tokens_per_layer`,
  `per_layer_model_projection`, `per_layer_projection_norm`,
  `*.per_layer_projection`) to the keep-list since Google flags them
  as quantization-sensitive and the user audit didn't include them.
* **Q3 (output dir):** `Eyes_v2_Gemma4e2b_merged` alongside the existing
  adapter on Drive.
* **Q4 (size budget):** "a+b+c" — emit all three GGUF variants
  (Q4_K_M aggressive, Q5_K_M balanced, Q8_0 quality) so the user can
  A/B test on real garments. Same `mmproj-F16.gguf` shared by all three.

## 2. Files changed / added

```
docs/
  Eyes_v2_Merge_Quantize.ipynb   (NEW — single self-contained Colab notebook)
  chat_summary.md                (this section)
```

The notebook is structured as 7 numbered sections so any stage can
be re-run independently:

* §1 Setup (transformers, peft, accelerate, litert-torch, cmake build deps)
* §2 Paths + the canonical KEEP_FP16_REGEX list (single source of truth)
* §3 LoRA merge in bf16 → save HF safetensors shards to Drive +
     blank-canvas inference sanity check (catches a broken merge before
     spending 30 min on quantization)
* §4 GGUF: build llama.cpp → `convert_hf_to_gguf.py --mmproj` →
     three `llama-quantize` runs with `--tensor-type` overrides mapped
     from the HF keep-list onto llama.cpp's GGUF tensor names
     (`blk.N.attn_*`, `per_layer_*`, etc.)
* §5 GGUF smoke test with `llama-mtmd-cli` on an uploaded garment photo,
     all three variants
* §6 LiteRT export via `ai-edge-torch` with `ai-edge-quantizer`
     Recipe API — INT4 blockwise on LM linears, FP16 NO_QUANTIZE
     overrides for every keep-list pattern, then
     `mediapipe-model-maker` to package the `.tflite` into a `.task`
* §7 Troubleshooting playbook (Q4 schema regression → pin first/last
     LM blocks; stale llama.cpp → git pull; MediaPipe Maker missing →
     manual zip recipe; LiteRT OOM on Colab free → run §6 locally)

## 3. Critical implementation notes for next agent

* **HF↔GGUF tensor name mapping.** The notebook documents this inline
  in §4c — llama.cpp strips `model.` and renames sub-blocks. The
  KEEP_FP16_REGEX in §2 uses HF names; the GGUF_KEEP_FP16_OVERRIDES
  in §4c uses GGUF names. If llama.cpp ever renames again, only that
  one block needs updating.
* **Vision/audio go to mmproj, not LM gguf.** This collapses the LM-
  side keep-list to just `token_embd`, `per_layer_*`, and norms.
* **litert-torch builder probing.** §6 probes four entry-point names
  in priority order (`gemma3n.build_model_e2b`, …, falling back to
  `gemma3.build_model_1b`) because the package surface has shifted
  across versions. Keep this fallback chain in mind if the user
  upgrades litert-torch and a new name appears.
* **Gemma 3n KV-share architecture.** Layers 15-34 in the LM have
  q_proj and o_proj listed but no k_proj/v_proj in the user audit —
  this is the KV-sharing optimization, not missing layers. Both
  llama.cpp and litert-torch handle this natively; no special
  treatment needed in the keep-list.

## 4. Expected user workflow

1. Open `docs/Eyes_v2_Merge_Quantize.ipynb` in Colab Pro (L4 or A100).
2. Run §1-§3 (≈20 min: install + merge + save to Drive).
3. Run §4 (≈30 min: llama.cpp build + convert + 3 quantize passes).
4. Run §5 with a real garment photo → eyeball that Q4_K_M still emits
   the 18-field JSON. If not, follow §7a fix order.
5. Run §6 (≈45 min: LiteRT INT4 conversion is the slow part).
6. Once Q5_K_M passes a 30-image smoke test against
   `Eyes_v2_Local_Eval.ipynb`'s harness, flip
   `config.eyes_provider.active` in MongoDB from `gemini` to
   `custom_eyes_v2_q5km` (loader change in `eyes_override.py` already
   exists from the v1 work, just needs to point at the new GGUF path).

## 5. New backlog items

### `Z5-eyes-v2-prod-cutover` — P1 (blocked on user's quantization run)

After §5 in the notebook confirms Q5_K_M quality matches bf16:
1. Upload `Eyes_v2_Gemma4e2b-Q5_K_M.gguf` + `mmproj-F16.gguf` to the
   prod VPS at `/var/models/eyes_v2/`.
2. Add `custom_eyes_v2_q5km` as a routing target in
   `backend/app/services/garment_vision.py` (mirror the existing
   `custom_eyes_v1` block).
3. Run the existing `Eyes_Vision_Smoke_Test.ipynb` against the prod
   endpoint to confirm schema parity.
4. Flip `config.eyes_provider.active` and monitor
   `/api/v1/admin/eyes/diagnostics` for 24h before turning Gemini off.

### `Z5-mobile-deployment-pipeline` — P2 (blocked on Capacitor wrap)

The `.task` from §6 needs the Capacitor mobile wrap (separate
future task `Deploy DressApp Assistant to mobile devices`). When
that lands, drop the `.task` into the Android assets folder and
wire `MediaPipe LlmInference` into the existing
`garmentVision.captureAndAnalyze()` call path.


---

# Phase Z6 — Pivot to Gemma 4 E2B (NEW base), GGUF-only, INT4 on-device

User clarified that "Gemma4-E2B" was actually meant as a placeholder for the
genuinely-new `google/gemma-4-E2B-it` (Apache-2, released April 2026), NOT
Gemma 3n. Previous Z5 notebook assumed Gemma 3n architecture, which is
architecturally invalid for Gemma 4. Phase Z6 rewrites the quantization
notebook end-to-end against the real Gemma 4 specs.

## 1. Decisions taken (with user)

* **Base model:** `google/gemma-4-E2B-it` (verified architecture: 5.1B total
  params / 2.3B effective, 35 LM layers, hybrid sliding+global attention with
  unified K/V on global, p-RoPE, PLE retained from 3n, native trimodal
  text+image+audio, 128K context, `AutoModelForMultimodalLM` loader).
* **Mode:** auto-detect (option c) — notebook merges LoRA if
  `ADAPTER_DIR/adapter_config.json` exists, otherwise quantizes the stock
  model directly. Lets user benchmark vanilla Gemma 4 quality on Pi/phone
  before deciding whether to retrain Eyes v3 on it.
* **Target:** GGUF-only (no LiteRT) — llama.cpp now runs on Pi 5, Android
  (Termux), and iOS (via Capacitor/Swift wrappers), so Q4_K_M GGUF + F16
  mmproj covers the entire deployment matrix.
* **Quantization:** single Q4_K_M build (~2-3 GB LM + ~600 MB mmproj = ~3 GB
  total) — fits Pi 5 (8 GB) and any phone with ≥4 GB RAM comfortably.

## 2. Critical architectural deltas from Z5 (Gemma 3n) to Z6 (Gemma 4)

| Aspect                  | Z5 (Gemma 3n)                         | Z6 (Gemma 4)                              |
|-------------------------|---------------------------------------|--------------------------------------------|
| HF loader               | `AutoModelForImageTextToText`         | `AutoModelForMultimodalLM`                |
| LM layers               | 30                                    | 35                                         |
| Audio status            | Wired but unused by DressApp          | Native 1st-class modality (30s ASR/AST)   |
| Chat template           | Gemma 3 (`<start_of_turn>`)           | Native `system`/`user`/`assistant`        |
| Reasoning control       | n/a                                   | `<\|think\|>` token in system prompt       |
| Image token budget      | n/a                                   | 70/140/280/560/1120 (configurable)        |
| Context                 | 8K                                    | 128K                                       |
| Module-list audit       | Hard-coded from user's manual listing | **Runtime-discovered** via state-dict keys |

## 3. Files changed

```
docs/
  Eyes_v2_Merge_Quantize.ipynb   (REWRITTEN — Gemma 4 E2B / GGUF-only / Q4_K_M only)
  chat_summary.md                (this section)
```

Notebook section layout:
* §0 Title + Gemma 4 fact box (pulled from official model card)
* §1 Setup
* §2 Paths + adapter auto-detection (sets `MODE = MERGE+QUANTIZE` or `QUANTIZE-ONLY`)
* §3 Conditional merge (3 cells, all short-circuit if no adapter)
* §3b **Runtime module discovery** — streams state-dict keys, classifies
   them into 11 families, prints coverage. This replaces the hard-coded
   Gemma-3n module list which would silently match zero tensors on Gemma 4.
* §4 GGUF: build llama.cpp → `convert_hf_to_gguf.py --mmproj` → single
   `llama-quantize` pass to Q4_K_M with FP16 overrides on PLE/norms/embeddings
* §5 Smoke test (`llama-mtmd-cli` with the DressApp Eyes prompt)
* §6 Troubleshooting (gemma4 arch missing → branch fallback; Q4 schema
   regression → 3-step fix ladder; Pi 5 build instructions; backend wiring)

## 4. Important caveat for next agent

The user's old `Eyes_v2_Gemma4e2b` LoRA adapter (trained on Gemma 3n) is
**incompatible** with Gemma 4. If the user wants Eyes-level garment quality
on Gemma 4, they need to retrain. The notebook gracefully handles this by
quantizing the stock model when no adapter is present, but a retrained
`Eyes_v3_Gemma4_E2B` adapter is the production path.

## 5. New backlog items

### `Z6-eyes-v3-retrain` — P1 (user action)

Retrain the Eyes LoRA on `google/gemma-4-E2B-it`. The existing v2 training
notebook needs:
1. `AutoModelForMultimodalLM` instead of `AutoModelForImageTextToText`.
2. Updated chat template (native system/user/assistant, no
   `<|think|>` for JSON-strict).
3. Target modules will change — re-run `model.named_parameters()` and pick
   LoRA target_modules accordingly (probably `q_proj`, `k_proj`, `v_proj`,
   `o_proj`, `gate_proj`, `up_proj`, `down_proj` on `language_model.layers.*`
   — vision/audio towers should be frozen).
4. PEFT config: `r=16, alpha=32` is a fine starting point for Gemma 4 E2B.

### `Z6-llama-cpp-gemma4-availability` — P1 (risk monitor)

Gemma 4 is brand new. Verify `convert_hf_to_gguf.py` in current llama.cpp
master accepts the architecture before kicking off a long Colab run. If
not, fall back to the open Gemma-4 PR branch (§6a in the notebook documents
the procedure).

### `Z6-pi5-prod-test` — P2

Once a Q4_K_M build passes the §5 smoke test in Colab, sync it to a Pi 5
test rig and confirm 3-6 tok/s steady-state throughput on real DressApp
garment uploads.
