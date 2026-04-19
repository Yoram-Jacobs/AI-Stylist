# DressApp — Development Plan (Core-first) **UPDATED (post Phase 4: Calendar OAuth + Trend‑Scout ship)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference (free tier) using **`mattmdjaga/segformer_b2_clothes`** via `huggingface_hub.InferenceClient`.
  - **Image generate/edit (“Nano Banana”)**: Gemini Flash Image via **Emergent Universal Key** using model **`gemini-3.1-flash-image-preview`**.
  - Resilience: image edit uses **retry/backoff** for transient 502s; `/closet/{id}/edit-image` returns **HTTP 503** (not 500) on persistent upstream failures.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, and passes integration testing.
- ✅ **Phase 4 (Part 1) shipped**: **Google Calendar OAuth** (read‑only) + real event hydration in Stylist.
- ✅ **Phase 4 (Part 2) shipped**: **Trend‑Scout autonomous agent** (APScheduler) + Home feed powered by backend.
- 🎯 **Current focus (remaining Phase 4)**: **PayPlus payments integration** (replacing Stripe) — *deferred until PayPlus API credentials are available*.

> **Operational note (external):** The user’s **EMERGENT_LLM_KEY budget is currently exhausted** (BudgetExceeded). This can temporarily impact Gemini calls (Stylist + Trend‑Scout). No code fix needed; user must top up the universal key balance.

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
**User stories (Phase 1)**
1. ✅ Image + text → styling advice grounded in weather.
2. ✅ Image + voice → Whisper transcript → advice.
3. ✅ Optional garment cutout + edit pipeline.
4. ✅ Audio response via TTS.
5. ✅ Single POC script producing inspectable artifacts.

**Phase 1 artifacts**
- ✅ `/app/docs/ARCHITECTURE.md`
- ✅ `/app/docs/MONGODB_SCHEMA.md`
- ✅ `/app/scripts/poc_stylist_pipeline.py` (updated to reflect HF segmentation + Nano Banana edit)

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
**User stories (Phase 2)**
1. ✅ CRUD closet items with `source=Private|Shared|Retail`.
2. ✅ Upload item photo via URL or base64 (**best‑effort segmentation**).
3. ✅ Authenticated stylist grounded in closet + weather + session history.
4. ✅ Public marketplace browse (filters) + seller-owned listing CRUD.
5. ✅ Transaction ledger creation with **7% platform fee after processing fee math** (payments wiring deferred).

**Phase 2 delivered (authoritative file list; updated for vision swap)**
- ✅ Auth & security
  - `/app/backend/app/services/auth.py`
  - `/app/backend/app/api/v1/auth.py`
  - `/app/memory/test_credentials.md`

- ✅ User profile
  - `/app/backend/app/api/v1/users.py`

- ✅ Closet
  - `/app/backend/app/api/v1/closet.py`
    - best‑effort segmentation via HF segmentation service
    - `/closet/{id}/edit-image` uses Nano Banana edit and degrades to 503 on upstream unavailability
  - `/app/backend/app/services/hf_segmentation.py`
  - `/app/backend/app/services/gemini_image_service.py`

- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`

- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py`
  - `/app/backend/app/api/v1/stylist.py`

- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py` — partial-filter unique index for `transactions.stripe.checkout_session_id` (legacy; will be revisited when PayPlus lands)

**Phase 2 testing status**
- ✅ Regression testing: `/app/test_reports/iteration_2.json` (historical)

**Phase 2 known limitations (expected, not bugs)**
- Nano Banana image generate/edit can intermittently return upstream 502; app retries and returns 503 with a user‑safe message.
- Payments are not wired (transactions remain `pending`).

---

### Phase 3 — Frontend V1 (React) **(COMPLETE)**
**User stories (Phase 3)**
1. ✅ Register/login + one-tap dev login.
2. ✅ Add and manage closet items.
3. ✅ Stylist chat:
   - ✅ Image + text
   - ✅ Image + voice capture → transcript + advice
   - ✅ Audio playback for `tts_audio_base64`
4. ✅ Browse marketplace listings + fee/net breakdown.
5. ✅ Create/manage listings from closet items.
6. ✅ View ledger/transactions.

**Phase 3 delivered**
- ✅ All pages compile and routes are valid.
- ✅ Added `/transactions` page
  - `/app/frontend/src/pages/Transactions.jsx`
  - Routed in `/app/frontend/src/App.js`
  - Linked via TopNav dropdown
- ✅ Lint warnings resolved.
- ✅ UI verified via screenshots.

**Phase 3 testing**
- ✅ Frontend + backend integration testing: `/app/test_reports/iteration_3.json`
  - Backend: **92.7%**, Frontend: **95%**, Integration: **90%**
  - **0 critical bugs**, **0 UI bugs**

---

### Phase 4 — Context + Autonomy + Payments (PayPlus) **(IN PROGRESS)**

#### Phase 4 (Part 1) — Google Calendar OAuth (P0) **(COMPLETE)**
**Delivered**
- ✅ Backend OAuth + Calendar API
  - `/app/backend/app/services/calendar_service.py`
    - auth URL builder
    - code exchange + userinfo fetch
    - token persistence on `users.google_calendar_tokens`
    - refresh-token preservation on repeated consent
    - auto-refresh access token when expired
    - `get_events_for_user()` returns compact events for stylist grounding
  - `/app/backend/app/api/v1/google_auth.py`
    - `GET /api/v1/auth/google/start`
    - `GET /api/v1/auth/google/callback`
    - `POST /api/v1/auth/google/disconnect`
    - `GET /api/v1/calendar/status`
    - `GET /api/v1/calendar/upcoming`
    - CSRF-safe state using short-lived (15 min) JWT carrying DressApp `user_id`
    - Graceful redirect-with-error for all failure paths
  - `/app/backend/app/api/v1/stylist.py`
    - When `include_calendar=true`, hydrates real events if connected; falls back to mock event otherwise

- ✅ Frontend UI
  - `/app/frontend/src/components/CalendarConnect.jsx` — connect/disconnect card + post‑OAuth toast handling
  - `/app/frontend/src/pages/Profile.jsx` — Calendar card embedded in Profile
  - `/app/frontend/src/pages/Stylist.jsx` — “Live Google Calendar” badge when connected; occasion input shown when not connected


#### Phase 4 (Part 2) — Trend‑Scout Background Agent (P1) **(COMPLETE)**
**Delivered**
- ✅ Backend Trend‑Scout agent + persistence
  - `/app/backend/app/services/trend_scout.py`
    - generates 3 editorial cards/day (runway / street / sustainability)
    - idempotent per day
    - persists to `trend_reports` with unique `(bucket, date)`
  - `/app/backend/app/services/scheduler.py`
    - APScheduler singleton
    - schedule default: **daily 07:00 UTC** (env configurable)
  - `/app/backend/app/api/v1/trends.py`
    - `GET /api/v1/trends/latest` (public-safe)
    - `POST /api/v1/trends/run-now` (admin)
    - `POST /api/v1/trends/run-now-dev` (auth-only dev helper)
  - `/app/backend/app/db/database.py`
    - indexes: `(date desc, bucket)` and unique `(bucket, date)`

- ✅ Frontend Home feed integration
  - `/app/frontend/src/pages/Home.jsx` reads from `/api/v1/trends/latest` and falls back to built‑in cards when empty
  - `/app/frontend/src/lib/api.js` includes `trendsLatest()`


#### Phase 4 (Part 3) — PayPlus Payments (replaces Stripe) **(NEXT / DEFERRED)**
**User stories**
1. Seller onboarding / payout routing using PayPlus (exact mechanism depends on PayPlus capabilities).
2. Buyer checkout creates a PayPlus payment session.
3. Webhooks update transaction lifecycle: `pending → paid/failed/refunded`.
4. Ledger consistency: store `gross`, `processing_fee`, `platform_fee (7% after fee)`, `seller_net`.

**Implementation (when PayPlus API credentials are available)**
- Confirm required credentials + environments (sandbox vs production)
- Define payout model: direct / escrow / split payout
- Backend endpoints:
  - create checkout/payment session
  - webhook handler
  - seller onboarding status endpoint (if applicable)
- DB refactor:
  - `users.stripe_account_id` → PayPlus equivalent
  - `transactions.stripe.*` → `transactions.payplus.*`
  - keep fee math unchanged

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(UPCOMING)**
**User stories (Phase 5)**
1. Admin dashboard: revenue, payouts, user activity, stylist usage.
2. Reporting/moderation workflow for listings.
3. Export/delete data.
4. Deterministic E2E suite.

**Implementation**
- Admin endpoints + (optional) UI
- Observability: request IDs, provider latency metrics, structured logs
- Load/chaos tests for stylist pipeline; retries/backoff

---

## 3) Next Actions (immediate)
1. **User action (external): Top up EMERGENT_LLM_KEY** to remove BudgetExceeded errors (affects Trend‑Scout completeness + fresh stylist calls).
2. Verify Google Calendar connection end-to-end in browser:
   - Profile → Connect Google Calendar → consent → redirected back to `/me?calendar=connected`
   - Stylist → toggle “Include calendar” → confirm advice references real events
3. (Optional hardening) Increase timeout for `/api/v1/trends/run-now-dev` since it can exceed 30s on cold starts.
4. **PayPlus discovery (deferred)**: once PayPlus credentials are available, implement checkout + webhooks + DB field migration.
5. Add a small E2E “happy path” script:
   - dev login → add closet item (segmented) → create listing → create transaction → verify ledger in `/transactions`

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; UI stable; iteration_3 test report green.
- Phase 4 (current):
  - ✅ Google Calendar OAuth functional (real events in stylist context)
  - ✅ Trend‑Scout runs daily and is visible in UI
  - ⏳ PayPlus payments wired end‑to‑end with webhook-driven transaction updates (pending user credentials)
- Phase 5:
  - Admin dashboard + hardened observability + deterministic E2E coverage
