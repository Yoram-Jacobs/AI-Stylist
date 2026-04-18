# DressApp — Development Plan (Core-first) **UPDATED (post Phase 2 ship)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture doc + MongoDB schema + Cloudflare `wrangler.toml` reference, plus backend scaffold + real-provider POC.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions, stylist w/ memory) with comprehensive regression testing.
- ⚠️ **fal.ai top-up remains pending**: SAM-2 segmentation + Stable Diffusion infill/edit are wired but cannot be validated until the fal.ai account balance is restored.
- 🎯 Current focus (Phase 3): Build the React frontend for Closet + Stylist + Marketplace using the existing backend API.

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
**User stories (Phase 1)**
1. ✅ Image + text → styling advice grounded in weather.
2. ✅ Image + voice → Whisper transcript → advice.
3. ⚠️ Optional garment edit (“change color…”) — code exists; blocked by fal.ai balance.
4. ✅ Audio response via TTS.
5. ✅ Single POC script producing inspectable artifacts.

**Phase 1 artifacts**
- ✅ `/app/docs/ARCHITECTURE.md`
- ✅ `/app/docs/MONGODB_SCHEMA.md`
- ✅ `/app/docs/wrangler.toml` (reference)
- ✅ `/app/scripts/poc_stylist_pipeline.py`

**Phase 1 follow-up (still pending)**
- ⚠️ Top up fal.ai at https://fal.ai/dashboard/billing (or provide a new `FAL_KEY`) and rerun:
  - `python scripts/poc_stylist_pipeline.py`
  - This flips segmentation + infill checkpoints to ✅.

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
**User stories (Phase 2)**
1. ✅ CRUD closet items with `source=Private|Shared|Retail`.
2. ✅ Upload item photo via URL or base64 (best-effort segmentation).
3. ✅ Authenticated stylist grounded in closet + weather + session history.
4. ✅ Public marketplace browse (filters) + seller-owned listing CRUD.
5. ✅ Transaction ledger creation with **7% after Stripe processing fee** logic (Stripe Connect checkout deferred to Phase 4).

**Phase 2 delivered (authoritative file list)**
- ✅ Auth & security
  - `/app/backend/app/services/auth.py` — bcrypt + JWT encode/decode + FastAPI bearer deps + admin guard.
  - `/app/backend/app/api/v1/auth.py` — `/auth/register`, `/auth/login`, `/auth/me`, `/auth/dev-bypass`.
  - `/app/memory/test_credentials.md` — dev credentials (dev@dressapp.io / DevPass123!).

- ✅ User profile
  - `/app/backend/app/api/v1/users.py` — GET/PATCH `/users/me` (style_profile, cultural_context, home_location, voice, language).

- ✅ Closet
  - `/app/backend/app/api/v1/closet.py` — closet CRUD + ownership enforcement; best-effort fal.ai segmentation; `/closet/{id}/edit-image` variant generator.

- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py` — listing CRUD; public browse + filters; `/listings/fee-preview` public endpoint; automatic **Private→Shared/Retail** transition on create.
  - `/app/backend/app/api/v1/transactions.py` — create pending ledger, self-purchase rejection, auto-reserve listing, buyer/seller role filter.

- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py` — session get_or_create, message append, recent_messages, closet_summary_for.
  - `/app/backend/app/api/v1/stylist.py` — authenticated multimodal stylist + memory persistence + closet_summary hydration + `/stylist/history`.

- ✅ Data layer
  - `/app/backend/app/services/repos.py` — small Motor CRUD helpers.
  - `/app/backend/app/db/database.py` — **partial-filter unique index** for `transactions.stripe.checkout_session_id` (prevents DuplicateKeyError on nulls).

- ✅ Router wiring
  - `/app/backend/app/api/v1/router.py` — mounts auth/users/closet/listings/transactions/stylist under `/api/v1/*`.

**Phase 2 testing status**
- ✅ `testing_agent_v3` regression pass: `/app/test_reports/iteration_2.json`
  - 35 passing tests
  - 0 critical bugs
  - 0 minor issues
  - Explicitly confirmed:
    1) Multiple pending transactions back-to-back
    2) Multipart stylist call with a **real** image returns 200 with reasoning + TTS.
- ✅ Local smoke: `/app/scripts/smoke_phase2.py`.

**Phase 2 known limitations (expected, not bugs)**
- ⚠️ fal.ai balance exhausted → segmentation/edit gracefully degrade.
- Google Calendar OAuth not wired (mock event used when `include_calendar=true`).
- Stripe Connect Express checkout + webhooks not wired (transactions remain `pending`).
- Embeddings + vector retrieval not implemented yet (moved to Phase 4.5 / Phase 5 depending on priority).

---

### Phase 3 — Frontend V1 (React) **(NEXT)**

**User stories (Phase 3)**
1. As a user, I can register/login (and one-tap dev login in non-prod).
2. As a user, I can add and manage closet items (upload photo, tag, source).
3. As a user, I can chat with the stylist with:
   - Image + text
   - Image + voice capture (browser mic) → transcript + advice
   - Audio playback of the stylist response.
4. As a user, I can browse marketplace listings and view fee/net breakdown.
5. As a seller, I can create/manage listings from closet items.

**3.0 Design pass (MANDATORY before building UI)**
- Use `design_agent` to produce:
  - IA/site-map + navigation model
  - Core component library decisions (shadcn/ui + Tailwind)
  - Primary layouts (mobile-first: Closet grid, Stylist chat, Marketplace cards)
  - Interaction specs for uploads, loading, and error states

**3.1 Frontend scaffold**
- Create React app structure (Emergent frontend conventions).
- Add shadcn/ui + Tailwind config.
- Add routing (React Router) with protected routes.
- Implement API client:
  - base URL `/api/v1`
  - bearer token injection
  - typed request wrappers for: auth, users, closet, listings, transactions, stylist

**3.2 Screens (MVP)**
- Auth
  - Login
  - Register
  - “Dev Login” button (calls `/api/v1/auth/dev-bypass` when enabled)
- Closet
  - Closet grid + filters (source/category/search)
  - Add item form (URL upload now; base64/camera later)
  - Item detail (edit fields, delete)
- Stylist
  - Chat UI with attachments
  - Image picker
  - Voice capture (webm) and submit as multipart
  - Audio playback for `tts_audio_base64`
  - History view (loads `/api/v1/stylist/history`)
- Marketplace
  - Browse listings (public)
  - Listing detail
  - Create listing (seller flow) + fee preview display
  - Transactions list (buyer/seller)

**3.3 Media handling in UI**
- For Phase 3 MVP, treat media as:
  - remote image URLs (preferred)
  - base64 MP3 returned by stylist endpoint → convert to Blob → audio element
- Explicit error messaging for fal.ai unavailability (segmentation/edit skipped).

**3.4 Frontend testing**
- Add minimal E2E checks:
  - dev login → create closet item → create listing → buyer creates transaction
  - stylist: image+text call returns advice + audio playback works
- Run `testing_agent_v3` for frontend integration once screens exist.

**3.5 Stretch: streaming voice UX**
- Implement backend WebSocket proxy usage for Deepgram streaming TTS (already scaffolded in service layer).
- UI: stream audio chunks while LLM output streams (requires server-side streaming for Gemini; not implemented yet).

---

### Phase 4 — Payments + OAuth + Trend-Scout
**User stories (Phase 4)**
1. Seller onboarding via Stripe Connect Express; store `stripe_account_id`.
2. Buyer checkout creates Stripe Checkout Session w/ split payout via `transfer_data`.
3. Ledger consistency: store `gross`, `stripe_fee`, `platform_fee(after stripe fee)`, `seller_net`.
4. User connects Google Calendar via OAuth 2.0; stylist includes real events.
5. Daily Trend-Scout summary available for admin.

**Implementation**
- Stripe Connect Express
  - onboarding endpoints + webhooks
  - Checkout Session creation using `transfer_data.destination = seller.stripe_account_id`
  - ensure 7% fee computed **after** Stripe processing fee
- Google Calendar OAuth
  - auth start + callback routes
  - token storage in `users.google_oauth` + refresh flow
- Trend-Scout Agent
  - APScheduler job
  - store `trend_reports`

---

### Phase 5 — Admin + Hardening + Comprehensive E2E
**User stories (Phase 5)**
1. Admin revenue + payouts dashboard.
2. Admin user activity + stylist usage.
3. Export/delete data.
4. Listing reporting + moderation workflow.
5. Deterministic E2E suite.

**Implementation**
- Admin endpoints + (optional) UI
- Observability: request IDs, provider latency metrics, structured logs
- Load/chaos tests for stylist pipeline; retries/backoff
- Vector retrieval (embeddings) if prioritized here instead of Phase 4.5

## 3) Next Actions (immediate)
1. **Start Phase 3 design** with `design_agent` (IA + component plan + mobile-first layouts).
2. Scaffold React frontend + API client.
3. Implement screens: Auth → Closet → Stylist → Marketplace.
4. Keep fal.ai top-up as a user action item (non-blocking for frontend).

## 4) Success Criteria
- Phase 1: ✅ shipped; fal.ai validation pending (balance).
- Phase 2: ✅ shipped and tested (iteration_2: 0 critical/minor bugs).
- Phase 3: MVP frontend can:
  - authenticate
  - manage closet
  - call stylist (image+text, image+voice)
  - play TTS audio reliably
  - browse/create listings and create pending transactions
- Phase 4: Stripe Connect Express + Google OAuth fully functional.
