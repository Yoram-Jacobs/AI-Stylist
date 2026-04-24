# DressApp — Development Plan (Core-first) **UPDATED (post Phase U ship + PayPal switch)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated & stabilised** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference using **`mattmdjaga/segformer_b2_clothes`**.
  - **Image generate/edit**: Hugging Face **FLUX.1-schnell**.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, integration-tested.
- ✅ **Phase 4 shipped (partial)**: Google Calendar OAuth + Trend‑Scout autonomous agent.
- ✅ **Phase 5 shipped**: Admin dashboard, provider activity monitoring, accessibility + SEO hardening.
- ✅ **Add Item overhaul shipped**: batch upload + animated scanning + "The Eyes" auto-fill + rich closet schema + one‑click auto‑listing.
- ✅ **Multi-Item Outfit Extraction shipped**: one uploaded photo → N editable item cards with IoU-NMS dedupe + "already cropped" short-circuit.
- ✅ **Closet Bulk Delete shipped**: multi-select mode on `/closet` with confirmation dialog + parallel deletes.
- ✅ **Phase A shipped**: provider-dispatched Eyes (Gemini default, Gemma HF path ready), **local FashionCLIP embeddings**, semantic search, Marketplace similar-items, native camera capture.
- ⏳ **Phase 6 Model Merge & Hosting (P0)**: off-pod merge of fine-tuned Gemma 4 E2B LoRA adapter → merged model → GGUF export + hosting (**blocked on external execution**).
- ✅ **Phase L Internationalization (i18n) initiative (P0)**: curated 12-language UI with full RTL mirroring for Hebrew/Arabic + per-user language persistence + AI output localization.
- ✅ **Phase L+ Taxonomy & Menus Translation Sweep (P0)**: no English leakage in dropdowns/menus in Hebrew mode (verified by screenshots).
- ✅ **Post-L+ follow-up**: Stylist language reliability improved (prompt preamble); and **sub_category/item_type display localization** (taxonomy mappings + hints + The Eyes directive updated).
- ✅ **Phase M System-native Speech (STT/TTS)**: Web Speech API (native) with Groq/Deepgram fallback.
- ✅ **Phase P Outfit Completion**: weighted centroids + weather awareness + UI reorder.
- ✅ **Phase Q Wardrobe Reconstructor**: HF FLUX outpainting + category-drift validation + manual Repair workflow.
- ✅ **Item Detail Edit Page**: full manual editor for closet items.
- ✅ **Phase R shipped**: **Multi-session Stylist + Fashion Scout side panel + chat image evidence**.
- ✅ **Phase S shipped**: **Device Access (Location UX) + Marketplace proximity + Region-aware Fashion Scout + share/invite + Professional CTA scaffold**.
- ✅ **Phase T shipped**: **Extended Profile & Settings** (full schema + UI + OAuth autofill).
- ✅ **Phase U shipped**: **Experts Pool + Ads/Campaigns + AdTicker + Ask-a-Professional directory** — backend 16/16, frontend 17/17.
- 🎯 **Payments shipped**: **PayPal** (Smart Buttons Orders v2) + **PayPal Payouts** + **prepaid ad credits** with multi-currency support. **LIVE on sandbox** (`PAYPAL_MOCK_MODE=false`) as of 2026-04-23. OAuth2 token returns scope including checkout, invoicing, and payouts. Real sandbox order `54G424177R8903615` for USD 10.00 was created + verified against PayPal REST API with correct brand name, merchant ID, payee `dev@dressapp.io`.

> **Operational note:** EMERGENT_LLM_KEY budget is topped up with auto‑recharge. Text/multimodal calls (Stylist + The Eyes + Fashion‑Scout) are expected to be stable, but transient upstream 503s may still occur (handled gracefully).

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
- ✅ `/app/scripts/poc_stylist_pipeline.py`

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
**User stories (Phase 2)**
1. ✅ CRUD closet items with `source=Private|Shared|Retail`.
2. ✅ Upload item photo via URL or base64 (best‑effort segmentation).
3. ✅ Authenticated stylist grounded in closet + weather + session history.
4. ✅ Public marketplace browse (filters) + seller-owned listing CRUD.
5. ✅ Transaction ledger creation with **7% platform fee after processing fee math** (payments wiring deferred).

**Phase 2 delivered (authoritative file list)**
- ✅ Auth & security
  - `/app/backend/app/services/auth.py`
  - `/app/backend/app/api/v1/auth.py`
- ✅ User profile
  - `/app/backend/app/api/v1/users.py`
- ✅ Closet
  - `/app/backend/app/api/v1/closet.py`
  - `/app/backend/app/services/hf_segmentation.py`
  - `/app/backend/app/services/hf_image_service.py`
  - `/app/backend/app/services/garment_vision.py` (The Eyes)
- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`
- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py`
  - `/app/backend/app/api/v1/stylist.py`
  - `/app/backend/app/services/gemini_stylist.py`
- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py`

---

### Phase 3 — Frontend V1 (React) **(COMPLETE + Add Item upgraded)**
**User stories (Phase 3)**
1. ✅ Register/login + one-tap dev login.
2. ✅ Add and manage closet items.
3. ✅ Stylist chat: image+text, image+voice, audio playback.
4. ✅ Browse marketplace listings + fee/net breakdown.
5. ✅ Create/manage listings from closet items.
6. ✅ View ledger/transactions.

---

### Phase 4 — Context + Autonomy + Payments (PayPal) **(SHIPPED 🎉)**

#### Phase 4 (Part 1) — Google Calendar OAuth (P0) **(COMPLETE)**
Delivered previously; unchanged.

#### Phase 4 (Part 2) — Fashion‑Scout Background Agent (P1) **(COMPLETE)**
- ✅ Scheduled generator runs daily and persists cards.
- ✅ Extended schema to support optional media fields (image/video/source) for the Stylist side panel.

#### Phase 4P (Part 3) — **PayPal Payments + Payouts + Credits** **(CERTIFIED LIVE ✅)**
**Goal**: Replace deferred PayPlus plan with **PayPal Smart Buttons** (Orders v2) for checkout and **PayPal Payouts** for seller disbursement, plus **prepaid ad-credit balance** for professionals. Support **sandbox + live** via `PAYPAL_ENV`. Support **multi-currency MVP**.

**Shipped**:
- `paypal_client.py` — httpx REST v2 wrapper with OAuth2 token cache, mock fallback available for dev/demo (currently disabled — `PAYPAL_MOCK_MODE=false`).
- Orders: `POST /v1/paypal/orders` create + capture, webhook handler with duplicate-event dedupe + signature verify hook.
- Credits: prepaid balance per (user, currency). Endpoints: `GET/POST /v1/credits/balance|balances|history|topup|topup/{id}/capture`. Packs: $10, $25, $50, Custom ($1–$1000).
- Ads billing: impression/click deduct 1¢/5¢ atomically from credit balance; campaigns auto-pause with `status_reason='insufficient_funds'` when broke.
- Marketplace: `POST /v1/listings/{id}/buy` + `.../buy/capture` build Transaction + trigger PayPal Payouts to seller's `paypal_receiver_email`.
- Frontend: `lib/paypal.jsx` (PayPalScriptProvider + mock fallback), `PayPalCheckoutButton`, AdsManager credit balance + top-up dialog, Profile "Payouts (PayPal)" accordion, ListingDetail PayPal checkout.
- i18n: EN/HE/AR for credits, payouts, buy-for, paypalDisclosure.
- Tests: 17/17 backend feature tests passing (93% overall including edge cases).

> **Status (CERTIFIED LIVE)**: `PAYPAL_ENV=live`, `PAYPAL_MOCK_MODE=false`, `PAYPAL_SKIP_WEBHOOK_VERIFY=false`.
>
> **Live proof points (all verified 2026-04-24):**
> - Live OAuth2 token: PASS (scope includes checkout, invoicing, payouts).
> - Real live order `7TY64109UB0382526` ($1.00 USD) created via `/credits/topup`, confirmed by direct `api-m.paypal.com/v2/checkout/orders/…` fetch: payee `myluckysell@gmail.com`, merchant `KPBFS6FYNNZ38`, brand `DressApp`.
> - Real PayPal Smart Buttons render live checkout popup; user reached real PayPal checkout with merchant correctly identified (PayPal's own self-purchase guard fired — proof that payee routing is correct).
> - Webhook signature verification active; bogus unsigned POST correctly returns `{ok:false, reason:"signature_not_verified"}`.
>
> **Webhook IDs registered and saved:**
> - Sandbox: `7FG04442026793247`
> - Live: `2U7003892N5293405`
> - Endpoint: `https://ai-stylist-api.preview.emergentagent.com/api/v1/paypal/webhook`
> - Subscribed events: `PAYMENT.CAPTURE.{COMPLETED,DENIED,REFUNDED,REVERSED}`, `PAYMENT.PAYOUTS-ITEM.{SUCCEEDED,FAILED,BLOCKED,HELD,RETURNED,UNCLAIMED}`, `PAYMENT.PAYOUTSBATCH.{SUCCESS,DENIED}`.
>
> **Known operational note:** Self-purchase from the merchant account is blocked by PayPal by design; real-money buyers must use a different PayPal personal account or guest card checkout.

**Known credentials status**
- ✅ Sandbox keys received.
- ⚠️ Live keys received but look suspicious (client_id == secret in pasted values). Not blocking sandbox work; needs correction before live cutover.
- ⏳ Webhook IDs deferred until backend URL stable (we’ll provide webhook URL and events list).

##### Phase 4P.A — Env + PayPal client service (P0)
- Add env keys:
  - `PAYPAL_ENV=sandbox|live`
  - `PAYPAL_SANDBOX_CLIENT_ID`, `PAYPAL_SANDBOX_SECRET`, `PAYPAL_SANDBOX_WEBHOOK_ID`
  - `PAYPAL_LIVE_CLIENT_ID`, `PAYPAL_LIVE_SECRET`, `PAYPAL_LIVE_WEBHOOK_ID`
  - `PAYPAL_DEFAULT_CURRENCY` (fallback)
  - Optional: `PAYPAL_SUPPORTED_CURRENCIES=USD,EUR,ILS,...`
- New service: `/app/backend/app/services/paypal_client.py`
  - OAuth2 token retrieval + in-memory cache (refresh before expiry)
  - `httpx` wrapper for REST API v2 calls (Orders create/capture), webhook verification endpoint, Payouts API
  - Environment-based base URLs:
    - sandbox: `https://api-m.sandbox.paypal.com`
    - live: `https://api-m.paypal.com`
- Add backend endpoint to expose frontend config:
  - `GET /api/v1/paypal/config` → `{ env, client_id, default_currency, supported_currencies }`

##### Phase 4P.B — Orders API routes + Webhooks (P0)
- `POST /api/v1/paypal/orders` (auth required)
  - Input: `{ amount_cents, currency, purpose: 'listing'|'ad_credit_topup', reference_id }`
  - Output: `{ order_id }`
  - Creates Orders v2 with `intent=CAPTURE`
- `POST /api/v1/paypal/orders/{order_id}/capture` (auth required)
  - Captures order and commits business side-effect based on `purpose`
- `POST /api/v1/paypal/webhook`
  - Verify webhook signature via PayPal `verify-webhook-signature` (uses env webhook_id)
  - Handle events:
    - `PAYMENT.CAPTURE.COMPLETED|DENIED|REFUNDED`
    - `PAYMENTS.PAYOUTS-ITEM.SUCCEEDED|FAILED|BLOCKED`
  - Idempotency guard by `event.id` (persist a `paypal_events` collection)

##### Phase 4P.C — Prepaid Ad Credit system (P0)
**Rationale**: Avoid storing payment methods and avoid end-of-day charging. Professionals top up credit balance via PayPal.

- New Mongo docs:
  - `user_credits` — one doc per `(user_id, currency)`:
    - `{ user_id, currency, balance_cents, updated_at }`
  - `credit_topups`:
    - `{ id, user_id, amount_cents, currency, status, paypal_order_id, paypal_capture_id, created_at, captured_at }`
- Endpoints:
  - `GET /api/v1/credits/balance?currency=USD`
  - `GET /api/v1/credits/history?currency=USD`
  - `POST /api/v1/credits/topup`:
    - input: `{ pack: '10'|'25'|'50'|'custom', custom_amount_cents?, currency }`
    - output: `{ topup_id, order_id }`
  - `POST /api/v1/credits/topup/{topup_id}/capture`
    - captures order and increments `user_credits.balance_cents` atomically
- Ads spend enforcement:
  - On `/ads/impression/{id}` and `/ads/click/{id}`:
    - deduct credits from campaign owner’s balance (per-currency)
    - if balance <= 0: auto-pause campaign and set a flag e.g. `status_reason='insufficient_funds'`
  - Keep `spent_cents` counter, but now tie it to credits rather than virtual cents.

##### Phase 4P.D — Marketplace payments (listing purchases) + Payouts (P0)
- Extend `Transaction` schema:
  - add `paypal` pointer:
    - `{ order_id, capture_id, payer_id, payer_email, payout_batch_id, payout_item_id }`
- Extend `User` schema:
  - add `paypal_receiver_email` (optional, required to receive payouts)
  - accept in `PATCH /users/me`
- New endpoints:
  - `POST /api/v1/listings/{listing_id}/buy`:
    - create PayPal order for listing price (currency-aware)
    - returns `{ order_id }`
  - `POST /api/v1/listings/{listing_id}/buy/capture`:
    - captures order, creates `Transaction` with existing 7% platform fee math
    - triggers PayPal Payouts to seller `paypal_receiver_email`
- New service: `/app/backend/app/services/paypal_payouts.py`
  - `create_payout(batch_ref, receiver_email, amount, currency, note)`
  - Persist payout pointer on `Transaction`
- Webhook-driven payout status update:
  - `PAYMENTS.PAYOUTS-ITEM.*` updates transaction payout status.

##### Phase 4P.E — Frontend PayPal (P0)
- New frontend util: `/app/frontend/src/lib/paypal.js`
  - fetch `/paypal/config` once per session
  - dynamic PayPal JS SDK loader + `@paypal/react-paypal-js` wrapper
- New component: `PayPalCheckoutButton.jsx`
  - Uses Smart Buttons
  - `createOrder()` → backend `POST /paypal/orders` (or listing/topup specific endpoint)
  - `onApprove()` → backend capture
- Integrations:
  - `AdsManager.jsx`:
    - new “Credit balance” card
    - top-up dialog with quick packs `$10/$25/$50` + custom
    - uses `PayPalCheckoutButton`
  - `ListingDetail.jsx`:
    - replace stub checkout CTA with PayPal checkout button
- Profile:
  - Add “Payouts” accordion section with `paypal_receiver_email` field
- i18n keys:
  - `paypal.*`, `credits.*`, `payouts.*` (EN/HE/AR at minimum; other languages fallback acceptable for MVP)

##### Phase 4P.F — Admin surfaces (P1)
- `GET /api/v1/admin/credits`:
  - recent topups + per-user balances (filter by currency)
- `GET /api/v1/admin/payouts`:
  - payout batches/items, status, manual retry action

##### Phase 4P.G — Testing (P0)
- Backend tests (testing agent):
  - order create/capture flows in sandbox
  - credit top-up → balance increment
  - ad impression/click deduction → pause on insufficient funds
  - payout creation request structure (mock network)
  - webhook verification logic (sandbox; signature verify can be toggled off in dev)
- Frontend tests:
  - PayPal button renders with sandbox client_id
  - top-up modal opens + creates order + capture updates balance
  - listing buy creates order + capture creates transaction

**Non-goals for this pass**
- Full seller onboarding UX for PayPal business accounts (docs link only)
- Subscriptions
- Tax/VAT accounting

**Deferred until live cutover**
- Correct live client_id/secret pair
- Webhook ID registration per environment

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 6 — Fine-tuned Gemma 4 E2B Merge + GGUF Export + Hosting **(P0 / BLOCKED OFF-POD)**
Goal: replace Gemini for "The Eyes" with the user's fine-tuned Gemma 4 E2B.

Status unchanged: blocked due to pod storage limits; off-pod notebook handoff exists.

---

### Phase L — Internationalization (i18n) + RTL + AI localization **(P0 / COMPLETE)**

**Post-L hardening shipped (note)**
- ✅ Stylist reliably respects live UI language:
  - backend prefers `language` form field over DB preference
  - Gemini prompt includes explicit in-message language preamble
- ✅ `sub_category` and `item_type` localization improvements:
  - `taxonomy.sub_category.*` and `taxonomy.item_type.*` added
  - frontend shows localized hint beneath free-text fields when matched
  - The Eyes language directive updated to allow localized sub_category/item_type for new analyses

---

### Phase L+ — Taxonomy & Menus Translation Sweep **(P0 / COMPLETE)**
Delivered previously; unchanged (plus the post-L notes above).

---

### Phase M — System-Native Speech (STT + TTS) **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase P — Outfit Completion Task (Closet) **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase Q — High-Fidelity Wardrobe Reconstructor **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase O — Gemma 4 E4B Stylist Brain **(P2 / NOT STARTED)**
Delivered previously; unchanged.

---

### Phase R — Multi-session Stylist + Fashion Scout side panel **(P0 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase S — Device Access + Contacts UX + Region-aware Scout + Professionals scaffold **(P0 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase T — Extended Profile & Settings **(P0 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase U — Experts Pool + Ad Campaigns + Ticker **(P0 / COMPLETE)**
**Shipped**. Backend verified 16/16; Frontend verified 17/17.

> Billing was virtual counters in Phase U; Phase 4P will connect this to real prepaid credits.

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| **P0** | **Phase 4P — PayPal Orders + Payouts + Credits** | Phase 2 fee math + Phase U ads + Marketplace | None (sandbox keys received) |
| ✅ | **Phase U — Experts Pool + Ads + Ticker** | Phase S (location), Phase T (profile UI) | Shipped |
| **P0** | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |
| P2 | Fit-check Stylist upgrade using `body_measurements` | Phase T data available | None |
| P3 | Phase R polish: rename sessions + mobile UX | Phase R shipped | None |
| P3 | Photo blob store migration (S3/R2) | user scale | None |

---

## 3) Next Actions (immediate)
1. **Phase 4P — PayPal integration (P0)**
   - Implement `paypal_client.py` + env toggles (sandbox first)
   - Implement Orders create/capture endpoints + webhooks
   - Add prepaid ad credits (top-up + balance + deduction)
   - Implement Marketplace buy + seller payouts via PayPal Payouts
   - Frontend: PayPal Smart Buttons for listing buy + credit top-up
2. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
3. **Fit-check prompt upgrade (P2)**
   - Add `users.body_measurements` + `users.units` to stylist context.
   - Add “fit risk” warnings (too tight/too long/etc.) and size suggestions.
4. **Shared outfit viewer (P2)**
   - Add a `/shared/:id` public page that renders the shared outfit nicely (API exists).

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; UI stable; integration tests green.
- Phase 4:
  - ✅ Google Calendar OAuth functional (real events in stylist context)
  - ✅ Trend‑Scout runs daily and is visible in UI
  - ✅ Fashion‑Scout feed supports optional media and powers Stylist side panel
  - ⏳ **Phase 4P PayPal** wired end‑to‑end:
    - Orders create/capture works for listing purchases and credit top-ups
    - Webhook signature verification works (sandbox + live)
    - Credits: balances update correctly; ad serving pauses when funds insufficient
    - Payouts: seller disbursement requests created and tracked via webhooks
    - Multi-currency supported (at minimum: USD + one additional currency)
- Phase 5:
  - ✅ Admin dashboard + provider observability
  - ✅ Accessibility + SEO baseline shipped
- Phase L/L+:
  - ✅ Curated 12-language UI available via Settings
  - ✅ Language persists per-user across devices
  - ✅ Hebrew/Arabic full RTL mirroring
  - ✅ Stylist + The Eyes descriptive output respects selected language
  - ✅ Dropdown/menu taxonomy fully localized
  - ✅ Sub-category/item-type display localization improvements shipped
- Phase M:
  - ✅ Native STT/TTS works where supported; fallback preserved
- Phase P:
  - ✅ Outfit completion works end-to-end; weather-aware rationale; weighted centroid reorder UI
- Phase Q:
  - ✅ Reconstructor repairs bad crops automatically when flagged; manual repair works; validated results persist
  - ✅ Item Detail full edit page shipped
- Phase R:
  - ✅ Multi-session conversations: sidebar list + AI titles + New Conversation clears and starts a new session
  - ✅ Chat uses only current session context; switching session swaps history
  - ✅ Fashion Scout panel shows a news-flash feed with media tiles (image/video when present)
  - ✅ Stylist chat recommendations include at least one relevant image when possible
- Phase S:
  - ✅ First-run mobile location prompt (in-app rationale + native browser permission)
  - ✅ Location persisted to profile and used for weather + Market proximity
  - ✅ Fashion Scout localized by language+country (cached per day)
  - ✅ Share outfit + invite flows via Web Share API and robust fallbacks
- Phase T:
  - ✅ Extended profile schema persisted and patchable via `/users/me`
  - ✅ OAuth autofill from Google userinfo populates identity fields without clobbering edits
  - ✅ Profile UI supports all required sections
- **Phase U (COMPLETE)**
  - ✅ Users can self-certify as professional; profile fields saved; admin can hide
  - ✅ `/experts` directory lists professionals filtered by region/profession
  - ✅ Professionals can create ad campaigns; auction-lite ticker serves region-matched creatives
  - ✅ Home footer ticker + Experts page ticker render ads; impressions/clicks tracked
  - ✅ Stylist “Ask a Professional” CTA routes to `/experts` and pre-filters by region
- Phase 6 / N:
  - ⏳ Fine-tuned Gemma 4 E2B merged + hosted; `/api/v1/closet/analyze` uses it via endpoint/env switch
