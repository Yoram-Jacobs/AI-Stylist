# DressApp — Development Plan (Core-first) **UPDATED (Wave 3 shipped: Shipping Fee + Transactions UI + APP_PUBLIC_URL hygiene)**

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

## 3) Next Actions (immediate)

### P0 — Next wave candidates
1. Swap payment support (optional): PayPal capture for swap shipping (only if community requests).
2. Swap reservation semantics hardening:
   - reserved vs removed policy on accept
   - timeout/release logic for stale accepted swaps

### P1
3. Transactions page quality-of-life:
   - search by listing title
   - per-kind empty states and summaries

### P2
4. Object storage migration (Mongo base64 bloat → R2/S3).
5. Phase O: Swap Stylist Brain to fine-tuned Gemma 4 E2B (blocked on fine-tuning + hosting).

### P3
6. Refactor `AddItem.jsx` into modules.

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

---

## Out of scope (deferred)
- Swap PayPal capture at propose-time (Wave 4+ if community requests it)
- Refund policy for captured donation shipping
- Transactions search by listing title (future QoL)
