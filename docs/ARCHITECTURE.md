# DressApp — Technical Architecture Document (Phase 1)

> **Version:** 0.1 (Phase 1 deliverable)  
> **Runtime:** Emergent FARM stack (FastAPI + React + MongoDB)  
> **Reference Runtime:** Cloudflare Workers + Durable Objects + Vectorize (see `wrangler.toml`)  
> **Status:** Documentation + backend scaffolding delivered; POC pipeline validates the core multimodal stylist flow.

---

## 1. System Overview

DressApp is a fashion ecosystem that combines three sub-systems into one cohesive product:

1. **Personal Closet** — the user's private, photo-indexed wardrobe with AI-assisted tagging and segmentation.
2. **Community Marketplace** — a sell / swap / donate layer that spans three item sources: **Private**, **Shared**, **Retail**. Real payments flow through Stripe Connect Express with a **7% platform commission taken after Stripe's own fees**.
3. **Generative AI Stylist Agent** — a multimodal, context-aware agent that consumes image + text/voice, weather, calendar, and cultural preferences, then produces outfit recommendations with spoken response (streaming TTS).

The original specification called for a Cloudflare Workers backend with the 2026 Agents SDK, Durable Objects and Vectorize. Per the user's direction in the Phase 1 clarification call, we are adapting that design to Emergent's FARM stack while preserving every architectural concept 1-to-1. The Cloudflare design remains canonical and is shipped as `wrangler.toml` for parity and future migration.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          React Frontend (Phase 3)                       │
│  Closet · Camera (SAM live preview) · Stylist Chat · Marketplace · Ads │
└───────────────┬──────────────────────────┬─────────────────────────────┘
                │ REST / SSE / WS          │
┌───────────────▼──────────────────────────▼─────────────────────────────┐
│                       FastAPI Edge Layer  (/api/v1/*)                   │
│   auth · closet · stylist (multimodal) · marketplace · admin · webhooks│
└───────────────┬──────────────────────────┬─────────────────────────────┘
                │                          │
    ┌───────────▼──────────┐   ┌───────────▼──────────┐
    │  Application Services │   │ Background Scheduler │
    │  (FARM equivalents    │   │  (APScheduler)       │
    │   of Durable Objects) │   │  Trend-Scout Agent   │
    └───────────┬──────────┘   └───────────┬──────────┘
                │                          │
┌───────────────▼──────────────────────────▼─────────────────────────────┐
│                            MongoDB (Motor)                              │
│  users · closet_items · listings · transactions · stylist_sessions ·    │
│  embeddings (Atlas Vector Search) · trend_reports · cultural_rules      │
└────────────────────────────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────────────┐
│                         External AI / Data Providers                     │
│  fal.ai (SAM-2 + Stable Diffusion)  · Groq (Whisper-v3)  ·               │
│  Deepgram Aura-2 (streaming TTS)    · Gemini 2.5 Pro (Universal Key)  ·  │
│  OpenWeatherMap · Google Calendar (OAuth)  · Stripe Connect Express      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mapping: Cloudflare Canonical Design → FARM Implementation

| Cloudflare 2026 Concept               | Purpose in DressApp                         | FARM Equivalent                                                                              |
|---------------------------------------|---------------------------------------------|----------------------------------------------------------------------------------------------|
| Cloudflare Worker entrypoint          | Edge request handler                        | `FastAPI` app with `/api` router                                                             |
| Agents SDK (2026)                     | Long-lived agent orchestration              | `StylistAgent` class in `app/services/logic.py` + persisted `stylist_sessions` collection    |
| Durable Object (per-user agent state) | Persistent per-user memory                  | MongoDB document `stylist_sessions[user_id]` with `conversation_history`, `outfit_feedback`  |
| Cloudflare Vectorize                  | Clothing / outfit embedding search          | MongoDB Atlas Vector Search index on `embeddings.vector` (fallback: cosine over stored vec)  |
| Workers AI / AI Gateway (TTS routing) | Multilingual TTS + model routing            | Direct Deepgram Aura-2 client + centralized `app/services/deepgram_service.py`               |
| Workers KV                            | Fast config / feature flags                 | MongoDB `config` collection with in-memory LRU cache                                         |
| Cron Triggers                         | Trend-Scout daily job                       | `APScheduler` with `CronTrigger`                                                             |
| R2 object storage                     | Image + audio artifacts                     | Phase-2 upgrade: S3-compatible (boto3) via Emergent; Phase-1 stores base64 in Mongo/disk     |
| Queues                                | Async job fan-out                           | MongoDB `jobs` collection polled by APScheduler workers                                       |

The `wrangler.toml` reference artifact in `/app/docs/wrangler.toml` describes exactly how this same app would be wired on Cloudflare — keeping a migration path open.

---

## 4. Core Modules

### 4.1 Stylist Pipeline (the "hardest path")

```
POST /api/v1/stylist   (multipart)
  ├─ image (required, jpeg/png/webp)
  ├─ text  OR  voice_audio (one required)
  ├─ do_infill, infill_prompt (optional)
  ├─ lat, lng (for weather)
  ├─ include_calendar (bool)
  ├─ language (ISO-639-1, default 'en')
  └─ voice_id (Aura-2 voice model, default aura-2-thalia-en)

        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. Transcribe (if voice)   → Groq Whisper-large-v3           │
│ 2. Segment garment          → fal.ai SAM-2 / rembg fallback  │
│ 3. (optional) Infill / edit → fal.ai Stable Diffusion i2i    │
│ 4. Fetch weather            → OpenWeatherMap (lat/lng)       │
│ 5. Fetch calendar (opt.)    → Google Calendar API            │
│ 6. Retrieve similar items   → MongoDB Vector Search          │
│ 7. Generate styling advice  → Gemini 2.5 Pro (Universal Key) │
│ 8. Synthesize voice reply   → Deepgram Aura-2 (WS streaming) │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
Response:
{
  transcript, segmented_image_url, infilled_image_url (opt),
  weather_summary, calendar_summary,
  outfit_recommendations[], reasoning_summary,
  shopping_suggestions[], do_dont[],
  tts_audio_url  (or base64 in POC)
}
```

The stylist route supports two-phase delivery:

1. **REST (/api/v1/stylist)** — returns a JSON envelope + `tts_audio_url` (Phase 1).
2. **WebSocket (/api/v1/stylist/ws)** — streams: transcript chunks → text deltas from Gemini → raw MP3 bytes from Deepgram Aura-2 (Phase 2). This is how the agent speaks while it is still thinking.

### 4.2 Closet Service

- CRUD for `closet_items` with `source` ∈ {`Private`, `Shared`, `Retail`}.
- On upload: kick off `fal.ai/sam2` segmentation, store segmented PNG, generate embedding (sentence-transformers CLIP-style image+text embedding in Phase 2), persist in `embeddings`.
- Auto-tagger (Gemini 2.5 Pro multimodal) produces `category`, `color`, `material`, `formality`, `season`, `cultural_tags[]`.

### 4.3 Marketplace Service

- Create listing from a `closet_item` (toggles `source` from `Private` → `Shared` / `Retail`).
- Browse endpoint filters by source, category, price, location.
- Purchase flow (Phase 4) creates a Stripe Checkout Session with `payment_intent_data.application_fee_amount` = 7% buffer **applied after** Stripe's 2.9% + $0.30 processing fee. Pseudocode:

```
stripe_fee      = round(gross * 0.029 + 0.30, 2)
net_after_stripe= gross - stripe_fee
platform_fee   = round(net_after_stripe * 0.07, 2)     # 7% after Stripe fees (the "buffer")
seller_net     = net_after_stripe - platform_fee
```

- Full ledger stored in `transactions`.

### 4.4 Trend-Scout Agent (background)

- APScheduler `CronTrigger(hour=6, minute=0)` daily job.
- Pulls RSS / curated sources, summarizes via Gemini 2.5 Pro, stores into `trend_reports`.
- Admin dashboard consumes `trend_reports` for the editorial surface.

### 4.5 Contextual Services

- **Weather** — `app/services/weather_service.py` uses `OPENWEATHER_API_KEY` and `(lat, lng)` to return `{ temp_c, feels_like_c, condition, humidity, wind, uv, forecast_24h[] }`.
- **Calendar** — `app/services/calendar_service.py` uses per-user `google_access_token` / `google_refresh_token` stored in the `users` document. Returns today's events with inferred `formality` heuristics (e.g. "1:1 coffee" → casual, "client presentation" → formal).
- **Cultural rules** — `cultural_rules` collection stores region + religion + occasion constraints, injected into the Gemini prompt as hard constraints.

---

## 5. Security, Privacy & Observability

- Secrets live only in `/app/backend/.env` (never committed). A `secrets_template.py` enumerates all required keys.
- JWT auth with `passlib[bcrypt]`. A `/api/v1/auth/dev-bypass` route is exposed behind the `ALLOW_DEV_BYPASS=true` flag so the test agent can exercise protected routes without real OAuth — documented to be removed before deployment.
- All provider calls emit structured logs with provider, latency (ms), and status. Stripe webhook signatures verified via `stripe.Webhook.construct_event`.
- PII minimization: only user email + hashed password + optional style preferences + Google OAuth tokens live in `users`. Images are stored as references (S3 keys / URLs) in Phase 2.

---

## 6. Deployment

DressApp ships **a single backend codebase** that serves two production targets with different ML capabilities:

### 6.1 Hetzner VPS — `dressapp.co` (full-fat)

- 4-core / 8 GB VPS · Docker Compose · Caddy 2 (auto Let's Encrypt) · MongoDB Atlas.
- `deploy/Dockerfile.backend` installs **both** `requirements.txt` (lightweight) **and** `requirements-ml.txt` (torch / transformers / rembg / scipy / accelerate).
- CPU-only torch is pre-pulled from `https://download.pytorch.org/whl/cpu` so we don't drag in CUDA wheels.
- `app/config.py` auto-detects torch + rembg via `importlib.util.find_spec` and turns `USE_LOCAL_CLOTHING_PARSER=true`, `AUTO_MATTE_CROPS=true`. Local SegFormer-b2-clothes + rembg run inside the pod.

### 6.2 Emergent host — `ai-stylist-api.emergent.host` (cloud-only ML)

- Auto-managed Kubernetes pod, 250 m CPU / 1 Gi RAM. Cannot host the local ML stack (torch alone exceeds the disk/RAM budget).
- Only `requirements.txt` is installed by the Emergent build pipeline (no torch / transformers / rembg / cuda-*).
- Auto-detection in `app/config.py` flips `USE_LOCAL_CLOTHING_PARSER=false`, `AUTO_MATTE_CROPS=false`. The analyse pipeline transparently falls through to:
  - **Multi-item detection** → Gemini Nano Banana (`garment_vision._gemini_detect`).
  - **Single-item analysis** → Gemini 2.5 Pro multimodal.
  - **Background matting** → returns `None`; caller keeps the original crop.
- Live deploy-mode probe: `GET /api/v1/closet/analyze/version` exposes `torch_installed`, `rembg_installed`, `use_local_clothing_parser`, `auto_matte_crops` so you can confirm at-a-glance which mode is live.

### 6.3 Backend concurrency guard (both deploys)

The heavy `analyze_outfit` / `analyze` / `reanalyze` paths share a single process-wide `asyncio.Semaphore(1)` (`_ANALYZE_LOCK` in `api/v1/closet.py`). This serialises any inbound parallel request — multiple browser tabs, future client-side concurrency creep, retries — so a memory-constrained VPS never gets blown up by simultaneous heavy ML runs. Sub-crops within a *single* call still run concurrently via the inner Semaphore in `analyze_outfit`.

### 6.4 Re-analyse endpoint

`POST /api/v1/closet/{item_id}/reanalyze` re-runs The Eyes against an item's stored image (segmented → reconstructed → original fallback chain) and patches **only** the analyser-owned fields (title, taxonomy, weighted `colors[]`, weighted `fabric_materials[]`, condition, tags, …). User-managed fields (size, price, currency, marketplace_intent, notes, purchase history) are preserved. Used by the Item Detail "Analyze" button after a Replace Photo (which intentionally skips auto-segmentation).

---

## 7. Cloudflare migration path

For a future Cloudflare migration, see `wrangler.toml` — all bindings (DO, Vectorize, KV, R2, secrets) are enumerated there.

---

## 8. Phase Roadmap (summary)

| Phase | Deliverable                                                                                    |
|-------|-----------------------------------------------------------------------------------------------|
| 1     | Architecture doc + MongoDB schema + wrangler.toml + backend scaffold + **POC pipeline green**   |
| 2     | Full CRUD (users / closet / listings / transactions) + vector search + stylist memory           |
| 3     | React frontend — camera, closet, stylist chat (WS streaming), marketplace                       |
| 4     | PayPal Live checkout + webhooks; Google Calendar OAuth; Trend-Scout                             |
| 5     | Admin dashboard (revenue, users, trends) + E2E hardening + observability                        |
| 6+    | Local SegFormer + rembg cutout pipeline, Phase R Stylist multi-image + OutfitCanvas, Phase S widened search, Phase T-Auth Google OAuth, duplicate detection, edit-page weighted taxonomy, batch-OOM serial guard |
| Now   | **Dual-deploy split** — `requirements-ml.txt` for Hetzner, lightweight `requirements.txt` for the Emergent host. Auto-detection in `app/config.py` chooses local SegFormer vs Gemini fallback per environment. |

---

## 9. Notes on stale section content

Sections 4.1 and 4.2 above reference the original Phase 1 design — `fal.ai/SAM-2`, Stripe, etc. The shipped product replaced these with:

- **Garment segmentation**: local SegFormer-b2-clothes + rembg (Hetzner) / Gemini multi-item detector (Emergent), not fal.ai.
- **Payments**: PayPal Live, not Stripe.
- **Stylist memory**: persisted `stylist_sessions` collection per Phase 2; the `StylistAgent` orchestrator lives in `app/services/stylist/`.

The original wording is preserved here for historical traceability against the Phase 1 contract. Section 6 above (Deployment) is the source of truth for the current runtime.

