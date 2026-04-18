# DressApp — Development Plan (Core-first) **UPDATED (post Phase 1 ship)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Deliver the required documentation artifacts and a working FARM backend scaffold.
- ✅ Prove the **core multimodal stylist pipeline** end-to-end (image→voice/text→context→Gemini→TTS) with real providers.
- ⚠️ Close remaining Phase 1 POC gap by re-validating **fal.ai SAM-2 segmentation + Stable Diffusion infill** once the fal.ai balance is topped up or a new `FAL_KEY` is provided.
- Prepare for Phase 2 by solidifying:
  - persistent stylist memory in Mongo (`stylist_sessions`/`stylist_messages`)
  - embeddings + vector retrieval
  - robust auth + user profile/preferences
  - marketplace CRUD primitives (listings/transactions) consistent with Stripe Connect Express later

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
**User stories (Phase 1)**
1. ✅ As a user, I can submit an image + text prompt and receive styling advice grounded in weather.
2. ✅ As a user, I can submit an image + voice note and receive the transcribed request + advice.
3. ⚠️ As a user, I can request an optional “edit garment” transformation and receive an updated image. *(Blocked only by fal.ai balance; code paths exist.)*
4. ✅ As a user, I can receive the advice as an audio response (TTS) in my chosen language.
5. ✅ As a developer, I can run a single script that exercises the whole pipeline and outputs artifacts for inspection.

**1.1 Web research (best practices / pitfalls)**
- ✅ Completed for: fal.ai, Groq Whisper-large-v3, Deepgram Aura-2 (WS streaming), Gemini via `emergentintegrations`, OpenWeatherMap.
- ✅ Stripe Connect Express patterns reviewed at the math/stub level; full integration deferred to Phase 4.

**1.2 Create integration playbooks (before coding)**
- ✅ fal.ai: model invocation via `fal_client.submit_async`, and **data-URL upload** to avoid CDN token 403s.
- ✅ Groq: Whisper-large-v3 transcription (multipart forwarding pattern).
- ✅ Deepgram Aura-2: REST TTS + WebSocket streaming proxy pattern.
- ✅ Gemini 2.5 Pro via Emergent Universal Key: multimodal prompt + strict JSON contract.
- ✅ OpenWeatherMap: lat/lng → current + forecast.

**1.3 Backend scaffolding (minimal but real)**
- ✅ Repo structure created under `/app/backend/app` with:
  - `config.py` centralized settings loader
  - `secrets_template.py` enumerating required env vars
  - `db/database.py` Motor client + idempotent `ensure_indexes()`
  - `models/schemas.py` Pydantic v2 models mirroring Mongo schema
  - `services/*` provider wrappers + `logic.py` orchestrator
  - `api/v1/stylist.py` + `api/v1/router.py`

**1.4 `/api/v1/stylist` multimodal endpoint (POC-capable)**
- ✅ Implemented: multipart handler supports **Image + Text** and **Image + Voice**.
- ✅ Flow implemented:
  1) Voice → Groq Whisper-large-v3
  2) Image → fal.ai segmentation (soft-fails gracefully)
  3) Optional infill/edit (soft-fails gracefully)
  4) Weather fetch (OpenWeatherMap)
  5) Calendar (Phase 1: mock event; Phase 4: OAuth)
  6) Gemini 2.5 Pro generates structured JSON advice
  7) Deepgram Aura-2 returns MP3 (base64 in response)
- ✅ Verified by curl against running backend on port **8001**.

**1.5 POC test script (hard gate)**
- ✅ `/app/scripts/poc_stylist_pipeline.py` created and executed.
- ✅ Produces artifacts in `/app/poc_artifacts`:
  - input image
  - Whisper transcript test audio
  - advice JSON outputs
  - Deepgram MP3 outputs
- ⚠️ fal.ai checks are **soft-skipped** when fal.ai account is locked due to exhausted balance.

**1.6 Phase-1 required documents (delivered now)**
- ✅ `/app/docs/ARCHITECTURE.md` — Technical Architecture Document with Cloudflare→FARM mapping.
- ✅ `/app/docs/MONGODB_SCHEMA.md` — Schema includes required **Source Tags** and **Financial Metadata** + index bootstrap.
- ✅ `/app/docs/wrangler.toml` — Cloudflare reference artifact (Durable Objects, Vectorize, KV, R2, Queues, Cron).

**Exit criteria (Phase 1)**
- ✅ POC script runs successfully and proves:
  - Deepgram TTS ✅
  - Groq Whisper ✅
  - OpenWeather ✅
  - Gemini multimodal + strict JSON ✅
  - `/api/v1/stylist` end-to-end ✅
- ⚠️ Remaining to make Phase 1 fully green: **fal.ai balance top-up** to validate SAM-2 segmentation + Stable Diffusion infill.

**Phase 1 follow-up (single action item)**
- **Unblock fal.ai**:
  - Top up at https://fal.ai/dashboard/billing **or** provide a new `FAL_KEY`.
  - Rerun: `python scripts/poc_stylist_pipeline.py`
  - Expect checkpoints **4** and **5** to flip from ⚠️ to ✅.

---

### Phase 2 — V1 App Development (backend-first MVP)
**User stories (Phase 2)**
1. As a user, I can create/update/delete closet items with `source=Private/Shared/Retail`.
2. As a user, I can upload an item photo and store raw + segmented images.
3. As a user, I can ask the stylist for outfit suggestions using my closet + today’s weather.
4. As a user, I can browse marketplace listings filtered by source tag and category.
5. As a seller, I can draft a listing and see estimated fees + net (using the “7% after Stripe fees” rule).

**2.1 Build core data layer**
- Implement CRUD endpoints + DB access layer for:
  - `users`, `closet_items`, `listings`, `transactions`, `stylist_sessions`, `stylist_messages`.
- Add validation and constraints:
  - enforce `source` semantics (`Private` in closet; marketplace uses `Shared|Retail`).
  - enforce immutable financial ledger fields on transactions.

**2.2 Expand stylist agent memory (Durable Object equivalent)**
- Persist turns in `stylist_messages` and update `stylist_sessions.turns/last_active_at`.
- Add feedback loop endpoints: “thumbs up/down”, “wore this outfit”, “never suggest X again”.
- Inject retrieved memory (recent outfits + preferences) into the Gemini prompt.

**2.3 Embeddings + vector retrieval (Vectorize equivalent)**
- Preferred: MongoDB Atlas Vector Search index on `embeddings.vector`.
- Fallback: store vectors in Mongo and compute cosine similarity in-process (optionally FAISS).
- Use retrieval in stylist prompt:
  - “similar to this item”
  - “items that pair well with X”

**2.4 Harden media handling**
- Add a minimal media abstraction:
  - Phase 2: store base64 only for POC; migrate to object storage references (S3-compatible) for production readiness.
- Validate image/audio types and enforce size limits.

**2.5 Testing**
- Integration tests for:
  - CRUD (users/closet/listings)
  - stylist endpoint (record/replay or live keys)
  - fee math (unit tests)

---

### Phase 3 — Frontend V1 (React)
**User stories (Phase 3)**
1. As a user, I can upload a clothing photo and see it saved in my closet.
2. As a user, I can chat with the stylist, attach an image, and hear audio playback.
3. As a user, I can toggle “edit garment” and see the generated result.
4. As a user, I can browse marketplace items and view a fee/net breakdown.
5. As a user, I can set preferences (language, voice, style profile).

- Build minimal screens: Closet, Stylist (multimodal), Marketplace Browse, Settings.
- Add robust error states for provider failures (especially fal.ai quota/balance).
- E2E test: upload → stylist advice → audio playback.

---

### Phase 4 — Payments + OAuth + Trend-Scout
**User stories (Phase 4)**
1. As a seller, I can onboard via Stripe Connect Express and store my `stripe_account_id`.
2. As a buyer, I can checkout and the seller receives net via `transfer_data`.
3. As a platform, I record `gross`, `stripe_fee`, `platform_fee(after stripe fee)`, `seller_net`.
4. As a user, I can connect Google Calendar and get event-aware outfit suggestions.
5. As an admin, I can view daily Trend-Scout summaries.

- Stripe Connect Express onboarding endpoints + webhook handling.
- Checkout Session creation using `transfer_data.destination = seller.stripe_account_id`.
- Apply platform take rate using the **7% buffer after Stripe fees** rule.
- Google Calendar OAuth: auth start/callback, token storage on `users.google_oauth`, refresh flow.
- APScheduler Trend-Scout agent + `trend_reports` persistence.

---

### Phase 5 — Admin + Hardening + Comprehensive E2E
**User stories (Phase 5)**
1. As an admin, I can see revenue, take-rate, and payout totals.
2. As an admin, I can see active users and stylist usage metrics.
3. As a user, I can export/delete my data.
4. As a user, I can report a listing and trigger moderation workflow.
5. As a developer, I can run a full E2E suite with deterministic fixtures.

- Admin dashboard endpoints + UI (if requested).
- Observability: structured logs, provider latency tracking, request IDs.
- Load/chaos tests for stylist pipeline; retry/backoff policies.

## 3) Next Actions (immediate)
1. **Unblock fal.ai** by topping up fal.ai balance or providing a new `FAL_KEY`.
2. Rerun: `python scripts/poc_stylist_pipeline.py` to validate segmentation + infill (checkpoints 4–5).
3. If you approve Phase 2: implement persistent stylist memory + CRUD for closet/marketplace + embeddings retrieval.

## 4) Success Criteria
- Phase 1 (already shipped):
  - ✅ `/api/v1/stylist` works with Image+Text and Image+Voice.
  - ✅ Real provider proof for Groq Whisper, Deepgram TTS, OpenWeather, Gemini 2.5 Pro.
  - ⚠️ fal.ai remains pending due to exhausted balance (code present; needs top-up).
- Phase 2 readiness:
  - provider wrappers remain modular
  - secrets handled safely via env + template
  - DB schema + indexes present
  - stylist memory + vector retrieval integrated into prompts
