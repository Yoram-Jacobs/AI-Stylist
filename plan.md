# DressApp — Development Plan (Core-first) **UPDATED (Wave 2 shipped: Swap + Donate + Email Landing + Listing Detail Enrichment)**

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
  - Templates live in `services/email_service.py`:
    - `sale_seller`, `sale_buyer`
    - `swap_request`, `swap_success`, `swap_denied`
    - `donation_both`
  - Sale emails are triggered from PayPal capture flow.

### ✅ Marketplace Wave 2 — Swap + Donate pipelines (JWT-signed email actions) — **SHIPPED**
Wave 2 shipped the first complete “non-buy” marketplace transaction flows:
1. ✅ **Swap pipeline**: propose → email accept/deny (JWT-signed) → confirm receipt → complete.
2. ✅ **Donation pipeline (MVP)**: claim donation → donor accept/deny via JWT email → confirmation email.
   - Note: **optional PayPal handling-fee capture is deferred** (planned for next wave).
3. ✅ **Transaction landing page**: a minimal page for accept/deny clicks from emails (auth-optional).
4. ✅ **Listing detail enrichment**: shows **size, description, condition** clearly and renders mode-aware CTAs.

**Decisions implemented (locked):**
- ✅ **JWT approach**: signed tokens using existing `JWT_SECRET` with dedicated `aud`.
- ✅ **Swap UX**: swap button opens a **modal** listing the user’s closet; user selects **1 offered item**.
- ✅ **Donation**: “Claim donation” wired to MVP accept/deny emails; PayPal handling-fee capture deferred.
- ✅ **Landing page**: minimal status banner + listing summary + “Back to Marketplace” CTA.
- ✅ **Self actions**: hide Swap/Donate on own listings.

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
  - expiry (implemented at 7 days for usability; can be tightened to 24h later)
  - single-use protection with persisted `jti` + `action_token_used`.

---

#### W2.1 — Backend schema updates (transactions) — **SHIPPED**
**File:** `app/backend/app/models/schemas.py`
- ✅ Added `Transaction.kind: "buy" | "swap" | "donate"` (default `"buy"`).
- ✅ Added nested subdocuments:
  - ✅ `Transaction.swap`: `offered_item_id`, `accepted_at`, `denied_at`, `lister_received_at`, `swapper_received_at`, `completed_at`, `action_token_jti`, `action_token_used`
  - ✅ `Transaction.donate`: `handling_fee_cents`, `accepted_at`, `denied_at`, `completed_at`, `action_token_jti`, `action_token_used`
- ✅ Extended `TxStatus` to include: `accepted`, `denied`, `shipped`, `completed` (legacy buy flows remain compatible).

---

#### W2.2 — Backend service: JWT action tokens — **SHIPPED**
**File:** `app/backend/app/services/action_tokens.py`
- ✅ `mint(...) → (token, jti)` and `verify(token, expected_decision=...)`.
- ✅ Dedicated audience: `aud="dressapp.tx_action"`.
- ✅ Single-use via persisted `jti` on tx and `action_token_used` on consumption.

---

#### W2.3 — Backend endpoints (Swap) — **SHIPPED**
**File:** `app/backend/app/api/v1/transactions.py`
- ✅ `POST /api/v1/transactions/swap`
  - validates listing active + not self
  - validates offered item belongs to swapper
  - creates `kind="swap"` transaction
  - emails lister via `email_service.swap_request(...)`
- ✅ `GET /api/v1/transactions/action?token=...&decision=accept|deny` (public)
  - verifies JWT + single-use
  - applies decision idempotently
  - sends follow-ups (`swap_success` / `swap_denied`)
  - 303-redirects to `/transactions/:id/landing?status=...`
- ✅ `POST /api/v1/transactions/{tx_id}/confirm-receipt`
  - both parties can confirm receipt
  - when both confirmed → marks completed, flips closet item ownership, closes listing.

---

#### W2.4 — Backend endpoints (Donate) — **SHIPPED (MVP)**
**File:** `app/backend/app/api/v1/transactions.py`
- ✅ `POST /api/v1/transactions/donate`
  - creates `kind="donate"` transaction
  - sends accept/deny email to donor (reuses swap_request layout)
  - on accept → sends `donation_both` to donor+recipient
- ⏳ PayPal handling-fee capture path: **deferred** (planned for next wave).

---

#### W2.5 — Public landing projection — **SHIPPED**
**File:** `app/backend/app/api/v1/transactions.py`
- ✅ `GET /api/v1/transactions/{id}/landing-summary` (public)
  - returns minimal transaction + listing fields for email landing page.

---

#### W2.6 — DB index fix (PayPal order id uniqueness) — **SHIPPED**
**File:** `app/backend/app/db/database.py`
- ✅ Migrated `transactions.paypal.order_id` uniqueness from `sparse=True` to `partialFilterExpression` (string only)
  - prevents duplicate-key errors for swap/donate transactions where `paypal.order_id` is null.

---

#### W2.7 — Frontend: ListingDetail enrichment + mode-aware CTAs — **SHIPPED**
**File:** `app/frontend/src/pages/ListingDetail.jsx`
- ✅ Always shows size/condition/category/mode badges + description block.
- ✅ Mode-aware primary CTA:
  - `sell` → PayPal buy
  - `swap` → “Propose a swap” (opens modal)
  - `donate` → “Claim this donation” (MVP request)
- ✅ Self-owned listings show “Manage in mine” only (CTAs hidden).

---

#### W2.8 — Frontend: Swap picker modal — **SHIPPED**
**File:** `app/frontend/src/components/SwapPickerModal.jsx`
- ✅ Shadcn Dialog + closet grid, single-select.
- ✅ Submits via `api.proposeSwap(...)`.

---

#### W2.9 — Frontend: Transaction landing page — **SHIPPED**
**Files:**
- `app/frontend/src/pages/TransactionLanding.jsx`
- `app/frontend/src/App.js`
- ✅ Route: `/transactions/:id/landing`
- ✅ Status banner (Accepted / Declined / Pending / Invalid)
- ✅ Listing summary includes size, condition, description.
- ✅ Works without auth (uses public landing-summary endpoint).

---

#### W2.10 — API client updates — **SHIPPED**
**File:** `app/frontend/src/lib/api.js`
- ✅ `proposeSwap(listingId, offeredItemId)`
- ✅ `claimDonation(listingId, handlingFeeCents)`
- ✅ `confirmReceipt(txId)`
- ✅ `getLandingSummary(txId)` (public)

---

#### W2.11 — Testing & release hygiene — **SHIPPED**
- ✅ Manual curl smoke tests passed (swap propose, accept/deny, token reuse, token tamper, donate).
- ✅ `testing_agent` report:
  - backend: **100% pass**
  - frontend: **60% pass** due to automated session expiry (testing artifact; no product bugs reported)
- ✅ `CHANGELOG.md` updated with Wave 2 entries.

---

## 3) Next Actions (immediate)

### P0 — Wave 3 follow-ups (next)
1. **Donation handling-fee via PayPal** (finish the deferred branch):
   - create PayPal order on claim when fee  > 0
   - capture endpoint
   - only send donor/recipient confirmation after capture
   - ensure idempotency and refunds policy.
2. **Transactions page polish**:
   - filter/group by `kind` and `status`
   - add clear labels for swap/donate vs buy
   - show confirm-receipt CTA when applicable.
3. **Environment URLs**:
   - ensure `APP_PUBLIC_URL` is correctly set per environment so email redirects point to the correct frontend (prod vs preview).

### P1
4. Tighten swap reservation semantics:
   - decide whether listing becomes `reserved` vs `removed` immediately on accept
   - add timeout/release logic for stale accepted swaps.

### P2
5. Object storage migration (Mongo base64 bloat → R2/S3).
6. Phase O: Swap Stylist Brain to fine-tuned Gemma 4 E2B (blocked on fine-tuning + hosting).

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
- ✅ Swap:
  - propose from listing detail
  - lister receives JWT-signed Accept / Decline
  - tokens have dedicated audience and single-use protection
  - accept/decline redirects to `/transactions/:id/landing`
  - both parties confirm receipt; swap completes, closet ownership flips, listing closes
- ✅ Donate (MVP):
  - claim donation
  - donor accept/deny via JWT email
  - donor/recipient receive confirmation email (`donation_both`) on accept
  - PayPal handling-fee capture is explicitly deferred
- ✅ UI:
  - listing detail shows size/description/condition
  - swap/donate CTAs hidden on own listings
  - landing page works even in logged-out browsers
