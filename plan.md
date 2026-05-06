# DressApp — Development Plan (Core-first) **UPDATED (Wave 3 shipped + Phase O Wave O.1 shipped + SPA eager-load caching shipped)**

## 1) Objectives

### ✅ Production stabilisation (dressapp.co) — **SHIPPED & VERIFIED**
- ✅ **Hetzner build fix**: pinned `protobuf==5.29.6` to resolve dependency conflict.
- ✅ Removed legacy post-analysis duplicate detection (`find_potential_duplicate`) to reduce ML spend.
- ✅ Atlas upgrade: production DB moved to **10GB Atlas M10**.
- ✅ Duplicate-system UX: pre-flight hash duplicate detection only; star auto-demotion when original deleted.

### ✅ UX polish (Wave 1) — **SHIPPED**
- ✅ Brand logo lockups (`BrandLogo.jsx`) added to Login + TopNav.
- ✅ Closet search bar polish:
  - debounced live search
  - clear button
  - active-state ring
- ✅ Category filter improvements:
  - case-insensitive
  - synonym mapping (e.g. `Footwear` → `shoes`)
- ✅ PWA/favicon/manifest icons wired.
- ✅ `CHANGELOG.md` drafted; guidance to tag `v1.0-stable`.

### ✅ Marketplace Wave 1 — **SHIPPED**
- ✅ Auto-retire linked marketplace listings when closet item is deleted.
- ✅ Auto-list closet items to marketplace when item `source` flips to **Shared**.
- ✅ Merchant card hydration on listing detail:
  - **PII-safe name fallback**: `display_name → company_name → first_name → (hide)`
  - location fallback: `listing.location → seller.home_location → seller.address`.
- ✅ Resend transactional email integration wired end-to-end.
  - Templates in `services/email_service.py`:
    - `sale_seller`, `sale_buyer`
    - `swap_request`, `swap_success`, `swap_denied`
    - `donation_both`
  - Sale emails triggered from PayPal capture flow.

### ✅ Marketplace Wave 2 — Swap + Donate pipelines (JWT-signed email actions) — **SHIPPED**
Wave 2 shipped the first complete “non-buy” marketplace transaction flows:
1. ✅ **Swap pipeline**: propose → email accept/deny (JWT-signed) → confirm receipt → complete.
2. ✅ **Donation pipeline (MVP)**: claim donation → donor accept/deny via JWT email → confirmation email.
3. ✅ **Transaction landing page**: minimal status UI after accept/deny clicks (auth-optional).
4. ✅ **Listing detail enrichment**: shows **size, description, condition** + mode-aware CTAs.

**Decisions implemented (locked):**
- ✅ **JWT action links** signed using `JWT_SECRET` with a dedicated `aud`.
- ✅ **Swap UX**: modal closet picker (single item offer).
- ✅ **Self actions**: hide Swap/Donate on own listings.

### ✅ Marketplace Wave 3 — Shipping Fee + Transactions UI + APP_PUBLIC_URL hygiene — **SHIPPED**
Wave 3 extended Marketplace beyond Wave 2 MVP with listing-level shipping, PayPal capture for donation shipping, and a polished transactions hub.

**Ethos enforcement (implemented):**
- ✅ **No handling fees for donations** (donations remain free; only optional shipping reimbursement).
- ✅ UI nudges local pickup and community connection:
  - “🌱 Prefer local pickup”
  - “Meet locally to skip the fee 🌱”

### ✅ Phase O — Stylist Provider Migration — Wave O.1 — **SHIPPED (v1.1.1 candidate)**
**Primary objective achieved:** The stylist “Brain” no longer relies on Google Gemini as the default provider.

- ✅ Primary stylist brain swapped from **Google Gemini 2.5 Pro** → **Alibaba Qwen-VL-Max-Latest** via DashScope (international endpoint).
- ✅ Provider abstraction introduced so future model swaps are config-driven (env var) rather than deep code surgery.
- ✅ End-to-end verified:
  - Qwen brain completion observed at ~**19.5s**
  - Full `/api/v1/stylist` call observed at ~**42s** total in preview environment

### ✅ SPA zero-delay navigation (Closet + Marketplace + Experts) — **SHIPPED & VERIFIED**
**Objective achieved:** Main directory pages no longer re-fetch/flash spinners on SPA back/forward navigation.

- ✅ Introduced a lightweight cached-store layer (`createCachedStore.js`) with:
  - eager prewarm
  - stale-while-revalidate
  - bounded LRU caching
  - mutation helpers (invalidate / upsert / remove)
- ✅ Closet: `closetStore.js` eager-loaded + incremental sync support.
- ✅ Marketplace: `marketplaceStore.js` (browseStore + myListingsStore) wired into `Marketplace.jsx`.
- ✅ Experts: `expertsStore.js` wired into `ExpertsDirectory.jsx` with a **draft/applied** filter pattern (typing doesn’t spam network).
- ✅ `AppLayout.jsx` prewarms all three stores at boot and resets on logout.
- ✅ Verified via frontend testing agent (`iteration_19`):
  - instant returns to `/market` and `/experts`
  - stale-while-revalidate works
  - no console errors attributable to app code

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 3 — Frontend V1 (React) **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 4 — Payments (PayPal) **(SHIPPED)**
Delivered previously; unchanged.

---

### Phase Z2 — Duplicate detection (pre-flight only) + cleanup **(SHIPPED)**
- ✅ Deterministic pre-flight duplicate detection using `source_sha256` and fallback `source_phash`.
- ✅ Removed legacy expensive post-analysis duplicate detector.
- ✅ Auto-demote duplicate ⭐ when the canonical/original item is deleted.

---

### Marketplace Wave 1 — Auto-publish + Merchant Card + Email wiring **(SHIPPED)**
- ✅ Auto-created listings (`Listing.auto_created`) when closet item is Shared.
- ✅ Auto-retire listing when linked closet item is deleted.
- ✅ Listing detail merchant card:
  - name fallback chain: `display_name → company_name → first_name → hide`
  - location fallback chain: `listing.location → home_location → address`
- ✅ Resend integration with templates + sale email dispatch on PayPal capture.

---

### Marketplace Wave 2 — Swap + Donate + Email landing **(SHIPPED)**

#### W2.0 — Goals + constraints (implemented)
- ✅ No PII exposure on public listing page.
- ✅ Email action links are safe:
  - JWT signed with `JWT_SECRET`
  - dedicated audience claim `aud="dressapp.tx_action"`
  - expiry (implemented at 7 days for usability)
  - single-use protection with persisted `jti` + `action_token_used`

#### W2.1 — Backend schema updates (transactions) — **SHIPPED**
**File:** `app/backend/app/models/schemas.py`
- ✅ Added `Transaction.kind: "buy" | "swap" | "donate"` (default `"buy"`).
- ✅ Added nested `swap` + `donate` sub-documents.
- ✅ Extended `TxStatus` with `accepted`, `denied`, `shipped`, `completed`.

#### W2.2 — Backend service: JWT action tokens — **SHIPPED**
**File:** `app/backend/app/services/action_tokens.py`
- ✅ `mint(...) → (token, jti)` and `verify(token, expected_decision=...)`.
- ✅ Dedicated audience: `aud="dressapp.tx_action"`.

#### W2.3 — Backend endpoints (Swap/Donate/Action/Landing) — **SHIPPED**
**File:** `app/backend/app/api/v1/transactions.py`
- ✅ `POST /api/v1/transactions/swap`
- ✅ `POST /api/v1/transactions/donate` (Wave 2: email-only accept/deny)
- ✅ `GET /api/v1/transactions/action` (public)
- ✅ `POST /api/v1/transactions/{tx_id}/confirm-receipt`
- ✅ `GET /api/v1/transactions/{tx_id}/landing-summary` (public)

#### W2.4 — DB index fix (PayPal order id uniqueness) — **SHIPPED**
**File:** `app/backend/app/db/database.py`
- ✅ Migrated `transactions.paypal.order_id` unique index from `sparse=True` to a `partialFilterExpression` (string only).

#### W2.5 — Frontend Wave 2 components — **SHIPPED**
- ✅ `ListingDetail.jsx` mode-aware CTA (Buy/Swap/Donate) + meta badges + description.
- ✅ `SwapPickerModal.jsx` (closet picker).
- ✅ `TransactionLanding.jsx` + route `/transactions/:id/landing` (auth-optional).
- ✅ `api.js` additions: `proposeSwap`, `claimDonation`, `confirmReceipt`, `getLandingSummary`.

---

### Marketplace Wave 3 — **Shipping Fee (listing-level) + Transactions UI polish + APP_PUBLIC_URL hygiene** — **SHIPPED**

**Wave 3 scope (user-confirmed & implemented):**
- ✅ **No “handling fee” concept for donations**. Donations remain free.
- ✅ Introduce **listing-level optional shipping fee**.
- ✅ Add community nudge: encourage local pickup / relationship-building.
- ✅ Transactions UI: tabs + multi-select status chips.
- ✅ APP_PUBLIC_URL: auto-derive when unset + explicit override when set.

#### W3A — Listing-level Shipping Fee + PayPal hookup — **SHIPPED**

**Goal achieved:** Shipping is a first-class, optional listing attribute. For donations, the *only* money component is optional shipping reimbursement.

**Backend (shipped)**
- ✅ **Schema:** `Listing.shipping_fee_cents: int = 0` (default 0, no cap)
- ✅ **DTOs:** added to `CreateListingIn` + `UpdateListingIn`
- ✅ **SELL flow (PayPal):**
  - PayPal `create_order` gross now includes shipping:
    - `amount = list_price_cents + shipping_fee_cents`
  - Returns line-item breakdown to frontend:
    - `list_price_cents`, `shipping_fee_cents`, `amount_cents`
- ✅ **DONATE flow:**
  - If `listing.shipping_fee_cents > 0`:
    - claim creates PayPal order for shipping reimbursement
    - capture required before donor is emailed
    - new endpoint: `POST /api/v1/transactions/donate/{tx_id}/capture?order_id=...`
  - If `listing.shipping_fee_cents == 0`:
    - keep email-only flow (no payment)
- ✅ **Deprecation / compatibility:**
  - `DonateClaimIn.handling_fee_cents` retained for backward compatibility but ignored for business logic.

**Frontend (shipped)**
- ✅ Create Listing form:
  - new shipping fee input (`shipping_fee_cents`) with community-first helper copy
  - “🌱 Prefer local pickup” nudges default to 0
- ✅ Listing detail:
  - shows shipping line if shipping_fee > 0
  - shows “🌱 Local pickup preferred — no shipping fee” when 0
- ✅ Donation claim UI:
  - shipping_fee == 0 → one-click claim (email donor)
  - shipping_fee > 0 → PayPal flow (pay shipping → capture → donor emailed accept/deny)
- ✅ Frontend API: `captureDonationShipping(txId, orderId)` added.

---

#### W3B — Transactions Page Polish — **SHIPPED**

**Goal achieved:** Transactions page works across buy/swap/donate and supports fast filtering.

**Frontend (shipped):** `app/frontend/src/pages/Transactions.jsx`
- ✅ Tabs by kind with counts:
  - `All / Buying / Selling / Swaps / Donations`
- ✅ Multi-select status chips:
  - `pending / accepted / denied / shipped / completed / paid / refunded`
- ✅ Row affordances:
  - kind-appropriate icon + label
  - status tone
  - inline **Confirm receipt** CTA on accepted swap/donate rows where the current user hasn’t confirmed

---

#### W3C — APP_PUBLIC_URL Hygiene — **SHIPPED**

**Goal achieved:** Email links + redirects resolve correctly across prod and preview environments.

**Backend (shipped)**
- ✅ Auto-derive base URL when `APP_PUBLIC_URL` is unset:
  - reads `X-Forwarded-Proto`, `X-Forwarded-Host`, `Host`
- ✅ Preserve explicit override:
  - if `APP_PUBLIC_URL` is set → always use it (prod lock)
- ✅ Refactor link builders:
  - `_action_url()` and `_landing_redirect()` accept FastAPI `Request`

**Docs (shipped)**
- ✅ Added `backend/.env.example` documenting env vars and precedence rules.

---

### Marketplace Stability Hotfix (v1.1.2 candidate) — **SHIPPED**
Out-of-band hotfix wave for the user-reported "items stuck on Private / can't delete listing" regressions. All bugs reproduced and validated.

**Backend (shipped)**
- ✅ `DELETE /api/v1/listings/{id}` is now coordinated cleanup:
  - hard-deletes the listing
  - resets the linked closet item: `marketplace_intent='own'`, `source='Private'`, `auto_listing_id=null`, `auto_listing_needs_completion=false`
  - guarded by ownership AND `closet_item.auto_listing_id == listing_id` to avoid de-linking unrelated rows
- ✅ `update_item` (PATCH /api/v1/closet/{id}) close_listing branch now also:
  - flips closet item `source` → `Private` on intent revert (unless caller passed an explicit `source`)
  - clears `auto_listing_id` + `auto_listing_needs_completion`
  - retires `reserved` listings too (was previously only `draft|active`)
- ✅ `create_item` (POST /api/v1/closet) now writes `auto_created=True` on the auto-created listing (fixes intent-revert teardown).
- ✅ Backfill + auto-list paths now map garment condition (`excellent` / `bad`) to listing condition vocab (`like_new` / `fair`).

**Frontend (shipped)**
- ✅ `Marketplace.jsx` → `MyListings`: per-card **Remove listing** button + top-bar **Sync from closet** button.
- ✅ `ListingDetail.jsx` owner view: **Remove from marketplace** button.
- ✅ `lib/api.js`: new `backfillMarketplaceListings()` helper.

**Verification**
- ✅ Backend: `iteration_18` testing agent run — 100% pass.

---

### SPA eager-load caching (Closet + Marketplace + Experts) — **SHIPPED & VERIFIED**

#### Cache layer + stores — **SHIPPED**
**Files:**
- ✅ `app/frontend/src/lib/createCachedStore.js`
- ✅ `app/frontend/src/lib/closetStore.js`
- ✅ `app/frontend/src/lib/marketplaceStore.js`
- ✅ `app/frontend/src/lib/expertsStore.js`

**What shipped**
- ✅ Stale-while-revalidate list stores with bounded LRU.
- ✅ Mutation helpers (`invalidate`, `upsertItem`, `removeItem`).
- ✅ `AppLayout.jsx` prewarm on auth resolve; reset on logout.

#### Page integrations — **SHIPPED**
- ✅ `Closet.jsx` (already shipped earlier) uses `closetStore`.
- ✅ `Marketplace.jsx` uses `browseStore` + `myListingsStore` via `useCachedList`.
- ✅ `ExpertsDirectory.jsx` uses `expertsStore` via `useCachedList` with draft/applied filters.

#### Verification — **SHIPPED**
- ✅ Frontend testing agent `iteration_19` — 100% pass on:
  - browse filter switching
  - tab switching
  - `/market → /closet → /market` instant return
  - `/experts → /home → /experts` instant return
  - experts search/apply/clear behavior

---

### Phase O — Stylist Provider Migration (Gemini → Qwen → Gemma) — **IN PROGRESS**

#### Wave O.1 — Stylist Brain swap to Qwen-VL-Max-Latest — **SHIPPED (v1.1.1 candidate)**

**What shipped**
- ✅ Primary stylist brain swapped from Google Gemini → DashScope Qwen-VL-Max-Latest (international endpoint).
- ✅ New `app/backend/app/services/qwen_client.py`:
  - async `httpx` client
  - base64 image support via data URIs
  - JSON response mode via `response_format={type:"json_object"}`
  - connect-only retries/backoff
  - 60s read timeout
- ✅ New `app/backend/app/services/stylist_brain.py`:
  - `QwenStylistBrain` (primary)
  - `GeminiStylistBrain` (adapter)
  - `FallbackBrain` (silent fallback)
  - future slot reserved for `GemmaStylistBrain`
- ✅ New env vars (documented in `backend/.env.example` and wired in `config.py`):
  - `STYLIST_PROVIDER` (default `qwen`)
  - `STYLIST_FALLBACK` (default `gemini`)
  - `DASHSCOPE_API_KEY`
  - `DASHSCOPE_BASE_URL` (default `https://dashscope-intl.aliyuncs.com/api/v1`)
  - `QWEN_BRAIN_MODEL` (default `qwen-vl-max-latest`)
  - `QWEN_EYES_MODEL` (default `qwen-vl-plus`)
- ✅ Integration points updated:
  - `services/logic.py` resolves stylist brain via `stylist_brain_service()`
  - provider name stored as `advice._meta.stylist_brain`

**Known notes**
- Qwen responses can be slower than Gemini; fallbacks handle timeouts when configured.

#### Wave O.2 — Migrate AddItem garment_vision “Eyes” + “Brain” to Qwen-VL — **NEXT (P0/P1)**
**Goal:** Fully migrate the AddItem multimodal pipeline off Gemini.

**Where to resume**
- `app/backend/app/services/garment_vision.py`

**Implementation outline**
1. Replace Gemini multimodal calls with DashScope Qwen-VL:
   - Eyes tier: `qwen-vl-plus`
   - Brain tier: `qwen-vl-max-latest`
2. Maintain JSON output contract compatibility with:
   - segmentation/background-removal pipeline
   - closet item card parsing
   - duplicate detection pre-flight pipeline
3. Add careful validation:
   - golden image fixtures
   - prompt hardening + schema validation
   - regression tests via curl/scripts

**Testing**
- Backend-only validation + targeted integration tests (curl/scripts).

#### Wave O.3 — Add Gemma4-E4B fine-tune into provider chain — **LATER (blocked on hosting)**
- Host the fine-tuned Gemma4-E4B on a 24/7 inference platform (HF Inference Endpoints / Modal / Runpod).
- Add `GemmaStylistBrain` implementation and set:
  - `STYLIST_PROVIDER=gemma`
  - `STYLIST_FALLBACK=qwen`

---

## 3) Next Actions (immediate)

### P0 — Next wave candidates
1. **Wave O.2:** migrate `garment_vision` Eyes + Brain from Gemini to Qwen-VL (high risk; AddItem pipeline).
2. Swap reservation semantics hardening:
   - reserved vs removed policy on accept
   - timeout/release logic for stale accepted swaps
3. Swap payment support (optional): PayPal capture for swap shipping (only if community requests).

### P1
4. Transactions page quality-of-life:
   - search by listing title
   - per-kind empty states and summaries

### P2
5. Object storage migration (Mongo base64 bloat → R2/S3).
6. Wave O.3: add fine-tuned Gemma4-E4B once 24/7 hosting is ready.

### P3
7. Refactor `AddItem.jsx` into modules.

---

## 4) Success Criteria

### Marketplace Wave 1 (already)
- ✅ Shared items auto-publish.
- ✅ Deleting closet item retires linked listing.
- ✅ Seller card shows only safe merchant info with correct fallback chain.
- ✅ Resend sale emails trigger on PayPal capture.

### Marketplace Wave 2 (shipped)
- ✅ Swap: propose → JWT accept/deny → landing → confirm receipt → completion.
- ✅ Donate (MVP): claim → donor accept/deny email → confirmation email.
- ✅ UI: listing detail shows size/description/condition; CTAs hidden on own listings; landing page works logged-out.

### Marketplace Wave 3 (shipped)
- ✅ Shipping fee:
  - `Listing.shipping_fee_cents` exists, is editable, and defaults to 0.
  - Sell PayPal charges include shipping and return a line-item breakdown.
  - Donate claim requires PayPal shipping reimbursement **only** when shipping fee > 0.
  - UI nudges local pickup: “🌱 Prefer local pickup” / “Meet locally to skip the fee 🌱”.
  - Donations remain free (no handling fee concept; backward-compat stub deprecated).
- ✅ Transactions UI:
  - Tabs + multi-select status chips.
  - Confirm receipt CTA appears appropriately for accepted swap/donate rows.
- ✅ Environment URLs:
  - Email action links and redirects land on the correct environment when `APP_PUBLIC_URL` is unset.
  - Explicit `APP_PUBLIC_URL` overrides derivation (prod lock).

### SPA eager-load caching (Closet + Marketplace + Experts)
- ✅ App boot prewarms Closet, Marketplace (browse + my listings), and Experts.
- ✅ Returning to `/closet`, `/market`, `/experts` shows cached results immediately (no spinner/skeleton flash).
- ✅ Filters apply correctly and do not cause infinite re-fetch loops.
- ✅ Mutations properly invalidate/update caches (e.g., delete listing removes from My Listings and browse invalidates).
- ✅ Verified via frontend testing agent `iteration_19`.

### Phase O — Stylist provider migration
- ✅ Wave O.1:
  - `/api/v1/stylist` uses Qwen-VL-Max-Latest by default.
  - Gemini remains available as fallback.
  - Provider selection controlled by env vars (`STYLIST_PROVIDER`, `STYLIST_FALLBACK`).
- ⏳ Wave O.2:
  - AddItem pipeline (`garment_vision`) produces the same closet item cards using Qwen.
- ⏳ Wave O.3:
  - Fine-tuned Gemma4-E4B can be toggled in as primary once hosted.

---

## Out of scope (deferred)
- Swap PayPal capture at propose-time (Wave 4+ if community requests it)
- Refund policy for captured donation shipping
- Transactions search by listing title (future QoL)
