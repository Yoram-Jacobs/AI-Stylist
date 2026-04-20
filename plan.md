# DressApp — Development Plan (Core-first) **UPDATED (post Phase 5: Admin + A11y/SEO + HF FLUX vision ship)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated & stabilised** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference (free tier) using **`mattmdjaga/segformer_b2_clothes`** via `huggingface_hub.InferenceClient`.
  - **Image generate/edit (replacement for Nano Banana)**: Hugging Face **FLUX.1-schnell** via `InferenceClient.text_to_image(provider='hf-inference')`.
    - Edit is implemented as **prompt-synthesised variant generation** using garment metadata (title/category/color/material/pattern/brand) + user instruction.
    - Typical latency: ~5–10s; output: **1024×1024 PNG** stored in `closet_items.variants[]`.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, and passes integration testing.
- ✅ **Phase 4 shipped (Part 1 & 2)**: Google Calendar OAuth (read-only) + Trend‑Scout autonomous agent.
- ✅ **Phase 5 shipped**: Admin dashboard (backend + UI) + provider activity monitoring + Accessibility + SEO hardening.
- 🎯 **Current focus (next milestone)**: **PayPlus payments integration** (replacing Stripe) — *deferred until PayPlus API credentials are available*.

> **Operational note:** The Emergent LLM Key budget issue is resolved (user topped up + enabled auto-recharge). Text LLM calls (Stylist + Trend‑Scout) are expected to be stable again.

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
- ✅ `/app/scripts/poc_stylist_pipeline.py` (updated to reflect HF segmentation + HF FLUX image variant generation)

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
    - `/closet/{id}/edit-image` now uses **HF FLUX** variant generation (prompt-synth) and returns **HTTP 503** on provider unavailability
  - `/app/backend/app/services/hf_segmentation.py`
  - `/app/backend/app/services/hf_image_service.py`

- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`

- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py` (now uses `hf_image_service` for optional infill)
  - `/app/backend/app/api/v1/stylist.py`
  - `/app/backend/app/services/gemini_stylist.py`

- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py`

**Phase 2 known limitations (expected, not bugs)**
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

**Phase 3 testing**
- ✅ Frontend + backend integration testing: `/app/test_reports/iteration_3.json`

---

### Phase 4 — Context + Autonomy + Payments (PayPlus) **(PARTIALLY COMPLETE / PAYPLUS DEFERRED)**

#### Phase 4 (Part 1) — Google Calendar OAuth (P0) **(COMPLETE)**
**Delivered**
- ✅ Backend OAuth + Calendar API
  - `/app/backend/app/services/calendar_service.py`
  - `/app/backend/app/api/v1/google_auth.py`
  - `/app/backend/app/api/v1/stylist.py` real-event hydration when connected
- ✅ Frontend UI
  - `/app/frontend/src/components/CalendarConnect.jsx`
  - `/app/frontend/src/pages/Profile.jsx`
  - `/app/frontend/src/pages/Stylist.jsx` (badge + occasion fallback)

#### Phase 4 (Part 2) — Trend‑Scout Background Agent (P1) **(COMPLETE)**
**Delivered**
- ✅ Backend Trend‑Scout agent + persistence
  - `/app/backend/app/services/trend_scout.py`
  - `/app/backend/app/services/scheduler.py`
  - `/app/backend/app/api/v1/trends.py`
  - `/app/backend/app/db/database.py` unique `(bucket, date)` index
- ✅ Frontend Home feed integration
  - `/app/frontend/src/pages/Home.jsx` reads `/api/v1/trends/latest`
  - `/app/frontend/src/lib/api.js` includes `trendsLatest()`

#### Phase 4 (Part 3) — PayPlus Payments (replaces Stripe) **(NEXT / DEFERRED)**
**User stories**
1. Seller onboarding / payout routing using PayPlus (depends on PayPlus capabilities).
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

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
**User stories (Phase 5)**
1. ✅ Admin dashboard: revenue, users, marketplace activity, stylist usage.
2. ✅ Monitoring for external providers (latency + error rate + last error tail).
3. ✅ Trend‑Scout monitoring + manual force-run.
4. ✅ Accessibility hardening pass.
5. ✅ SEO hardening pass.

**Phase 5 delivered**
- ✅ Admin Dashboard backend (gated by `require_admin`)
  - `/app/backend/app/api/v1/admin.py`
    - `/admin/overview`
    - `/admin/users` + `/{id}/promote|demote`
    - `/admin/listings` + `/{id}/status`
    - `/admin/transactions`
    - `/admin/providers` + `/{provider}/calls`
    - `/admin/trend-scout` + `/run`
    - `/admin/llm-usage` (best-effort, never 500)
    - `/admin/system` (redacted config + key presence)

- ✅ Provider activity tracker
  - `/app/backend/app/services/provider_activity.py`
  - wired into:
    - HF image gen (`hf-image`)
    - HF segmentation (`hf-segformer`)
    - Gemini stylist (`gemini-stylist`)
    - Groq Whisper (`groq-whisper`)
    - Deepgram TTS (`deepgram-tts`)
    - OpenWeather (`openweather`)

- ✅ Admin Dashboard UI
  - `/app/frontend/src/pages/Admin.jsx` (7 tabs: Overview/Providers/Trend‑Scout/Users/Listings/Transactions/System)
  - `/app/frontend/src/App.js` route: `/admin`
  - `/app/frontend/src/components/TopNav.jsx` adds “Admin” menu item for admin users only

- ✅ Accessibility
  - Skip link on first Tab (in App shell)
  - `<main id="main-content" tabIndex={-1}>` in `AppLayout`
  - Global `:focus-visible` outline
  - `prefers-reduced-motion` support
  - `aria-label` on icon-only nav elements

- ✅ SEO
  - `react-helmet-async` + per-route SEO
    - `/app/frontend/src/components/SeoBase.jsx`
    - `/app/frontend/src/App.js` wires `HelmetProvider` + `SeoBase`
  - Static assets:
    - `/app/frontend/public/robots.txt`
    - `/app/frontend/public/sitemap.xml`
    - `/app/frontend/public/manifest.json`

**Phase 5 testing**
- ✅ Comprehensive testing: `/app/test_reports/iteration_5.json`
  - Backend: **93.3%**, Frontend: **95%**, Overall: **94%**
  - **0 critical bugs / UI bugs / integration issues / design issues**
  - One LOW note: page title hydration latency (react-helmet-async updates after first paint; not a functional bug).

---

## 3) Next Actions (immediate)
1. **PayPlus discovery (deferred)**: when PayPlus credentials are available:
   - confirm sandbox/prod endpoints
   - confirm payout model
   - implement checkout + webhooks + DB field migration
2. Optional production hardening (nice-to-have, not blocking):
   - structured JSON logs + request IDs propagated through provider_activity
   - rate limits on stylist endpoints
   - deterministic E2E script (Playwright/Cypress) running the happy path:
     dev login → add closet item → edit variant → create listing → create transaction → verify ledger
3. (Optional) Add provider health “pings” (cheap GET probes) so Admin/Providers tab can show “configured but idle” vs “down”.

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; UI stable; integration tests green.
- Phase 4:
  - ✅ Google Calendar OAuth functional (real events in stylist context)
  - ✅ Trend‑Scout runs daily and is visible in UI
  - ⏳ PayPlus payments wired end‑to‑end with webhook-driven transaction updates (pending user credentials)
- Phase 5:
  - ✅ Admin dashboard + provider observability
  - ✅ Accessibility + SEO baseline shipped
  - ✅ Test report iteration_5 green