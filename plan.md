# DressApp — Development Plan (Core-first) **UPDATED (post Phase 3 ship + Vision stack swap)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference (free tier) using **`mattmdjaga/segformer_b2_clothes`** via `huggingface_hub.InferenceClient`.
  - **Image generate/edit (Nano Banana)**: Gemini Flash Image via **Emergent Universal Key** using model **`gemini-3.1-flash-image-preview`**.
  - Resilience: Nano Banana uses **retry/backoff** for transient 502s; edit endpoint returns **HTTP 503** (not 500) on provider downtime.
- ✅ **Phase 3 shipped**: React frontend compiles, is screenshot-verified, and passes integration testing.
- 🎯 **Current focus (Phase 4)**: **Google Calendar OAuth → Trend-Scout background agent → PayPlus payments integration** (replacing Stripe Connect).

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
**User stories (Phase 1)**
1. ✅ Image + text → styling advice grounded in weather.
2. ✅ Image + voice → Whisper transcript → advice.
3. ✅ Optional garment cutout + edit pipeline **implemented** (now HF + Nano Banana).
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
2. ✅ Upload item photo via URL or base64 (**best-effort segmentation**).
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
    - best-effort segmentation now via HF segmentation service
    - `/closet/{id}/edit-image` now uses Nano Banana edit and **gracefully degrades to 503** when upstream is unavailable
  - `/app/backend/app/services/hf_segmentation.py` — clothing cutout via HF `InferenceClient`
  - `/app/backend/app/services/gemini_image_service.py` — Nano Banana generate/edit via `emergentintegrations`

- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`

- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py` — orchestrator updated to use HF segmentation + Nano Banana when available
  - `/app/backend/app/api/v1/stylist.py`

- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py` — partial-filter unique index for `transactions.stripe.checkout_session_id` (legacy; will be revisited when PayPlus lands)

**Phase 2 testing status**
- ✅ Regression testing: `/app/test_reports/iteration_2.json` (historical)

**Phase 2 known limitations (expected, not bugs)**
- Nano Banana image generate/edit can intermittently return upstream 502; app retries and returns **503** with a user-safe message on persistent failures.
- Google Calendar OAuth not wired yet (mock calendar used when `include_calendar=true`).
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
- ✅ Missing page fixed: **`/transactions`** added
  - `/app/frontend/src/pages/Transactions.jsx`
  - Routed in `/app/frontend/src/App.js`
  - Linked via TopNav dropdown
- ✅ Lint warnings resolved.
- ✅ UI verified via screenshots (login, home, closet, stylist, market, transactions).

**Phase 3 testing**
- ✅ Frontend + backend integration testing: `/app/test_reports/iteration_3.json`
  - Backend: **92.7%**, Frontend: **95%**, Integration: **90%**
  - **0 critical bugs**, **0 UI bugs**
  - Note: One “flaky endpoint” observation was reported for `/closet/{id}/edit-image` in some curl auth scenarios; app-side flows are green.

---

### Phase 4 — Context + Autonomy + Payments (PayPlus) **(NEXT)**
**User stories (Phase 4)**
1. User connects Google Calendar via OAuth 2.0; stylist includes real events.
2. Daily Trend-Scout summary is generated in background and surfaced to users/admin.
3. Replace Stripe with **PayPlus** for marketplace payments.
4. Ledger consistency: store `gross`, `processing_fee`, `platform_fee(7% after fee)`, `seller_net` and map PayPlus webhooks to transaction lifecycle.

**Implementation (order confirmed)**
1) **Google Calendar OAuth (P0)**
- Backend:
  - Auth start + callback routes
  - Token storage in `users.google_calendar_tokens` (refresh flow)
  - Replace mock calendar events in stylist pipeline when connected
- Frontend:
  - Connect/disconnect button in Profile
  - Calendar status indicator in Stylist (optional)

2) **Trend-Scout background agent (P1)**
- Backend:
  - APScheduler job (daily)
  - Sources: fashion/news/retail signals (configurable) → Gemini summarization
  - Store in `trend_reports`
- Frontend:
  - Home page section reads from `/trend-reports` endpoint (or existing placeholder) and displays latest daily edit

3) **PayPlus payments integration (P1, replaces Stripe)**
- Define target PayPlus flows:
  - Seller payout model (direct/escrow/split payout)
  - Checkout initiation endpoint
  - Webhooks to update `transactions.status` (`pending` → `paid`/`failed`/`refunded`)
- Refactor existing Stripe-specific fields:
  - `users.stripe_account_id` → PayPlus equivalent
  - `transactions.stripe.*` → `transactions.payplus.*`
  - Keep fee math unchanged: platform fee remains **7% after processing fee**

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
- Optional: embeddings + vector retrieval if prioritized

---

## 3) Next Actions (immediate)
1. **Phase 4 (P0): Google Calendar OAuth** — implement backend OAuth flow + token storage + frontend connect UI.
2. **Phase 4 (P1): Trend-Scout Agent** — background schedule + persistence + Home feed.
3. **Phase 4 (P1): PayPlus discovery** — confirm required PayPlus credentials, webhook events, and payout model; then implement checkout + webhooks.
4. Add a small E2E “happy path” script that covers: dev login → add closet item (segmented) → create listing → create transaction → verify ledger in `/transactions`.

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; frontend runs without crashes; key flows screenshot-verified; iteration_3 test report green.
- Phase 4:
  - Google Calendar OAuth fully functional (real events in stylist context)
  - Trend-Scout runs daily and is visible in UI
  - PayPlus payments wired end-to-end with webhook-driven transaction status updates
- Phase 5:
  - Admin dashboard + hardened observability + deterministic E2E coverage
