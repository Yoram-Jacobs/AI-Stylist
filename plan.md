# DressApp — Development Plan (Core-first) **UPDATED (Wave 3 planned: Shipping Fee + Transactions UI + APP_PUBLIC_URL hygiene)**

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
- ✅ `POST /api/v1/transactions/donate` (MVP email-only accept/deny)
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

### Marketplace Wave 3 — **Shipping Fee (listing-level) + Transactions UI polish + APP_PUBLIC_URL hygiene** — **P0 / NEXT**

**Wave 3 scope (user-confirmed):**
- ✅ **No “handling fee” concept for donations**. Donations remain free per DressApp’s environmental ethos.
- ✅ Introduce **listing-level optional shipping fee**.
- ✅ Add a community nudge: encourage local pickup / relationship-building.
- ✅ Transactions UI: tabs + multi-select status chips.
- ✅ APP_PUBLIC_URL: auto-derive when unset + explicit override when set.

#### W3A — Shipping Fee (Listing-level) + PayPal hookup (P0)

**Goal:** Shipping becomes a first-class, optional listing attribute. This shipping fee is the only money component for donation listings.

**Backend changes**
- **Schema:**
  - Add `Listing.shipping_fee_cents: int = 0`.
- **DTOs:**
  - Add shipping fee to `CreateListingIn` and `UpdateListingIn`.
- **SELL flow (PayPal):**
  - Update PayPal `create_order` gross to include shipping:
    - `amount = list_price_cents + shipping_fee_cents`
  - Persist shipping fee on the transaction for transparency (either as part of `financial.gross_cents` or as an explicit field; decide implementation detail during coding).
- **DONATE flow:**
  - If `listing.shipping_fee_cents > 0`:
    - Claim opens a PayPal order for shipping only.
    - After PayPal capture succeeds → email donor accept/deny links (JWT).
    - If donor accepts → send `donation_both`.
  - If `listing.shipping_fee_cents == 0`:
    - Keep current email-only flow (no payment).
- **SWAP flow (Wave 3):**
  - Shipping fee is **display-only**; parties coordinate directly.
  - (Wave 4+ can add PayPal capture at propose-time if requested.)

**Deprecation / compatibility**
- Deprecate (but do not break) `DonateClaimIn.handling_fee_cents`:
  - Backend should ignore it for business logic once shipping is listing-driven.
  - Keep field temporarily so older clients don’t break.

**Frontend changes**
- Listing detail page displays shipping:
  - Copy: `Shipping: $X.XX · Meet locally to skip the fee 🌱`
  - For donate listings, CTA copy remains “Claim this donation”; payment step appears only when shipping fee > 0.

---

#### W3B — Transactions Page Polish (P0)

**Goal:** Make the transactions page useful across buy/swap/donate.

**Frontend:** `app/frontend/src/pages/Transactions.jsx`
- Add a **tab bar** with counts:
  - `All / Buying / Selling / Swaps / Donations`
- Add **filter chips** (multi-select) by status:
  - `pending / accepted / denied / shipped / completed`
- Per-row UI:
  - kind-appropriate icon + label
  - show listing title + mode
  - show "Confirm receipt" CTA when:
    - `kind=swap` and `status=accepted` (or shipped) and the current user hasn’t confirmed
    - `kind=donate` and `status=accepted` and the recipient hasn’t confirmed
- Filtering approach:
  - Client-side filtering over one fetch from `/api/v1/transactions` (no new backend endpoints required).

---

#### W3C — APP_PUBLIC_URL Hygiene (P0)

**Goal:** Ensure email links and redirects point to the correct environment.

**Backend**
- Auto-derive base URL when `APP_PUBLIC_URL` is unset:
  - Use FastAPI `Request` with `X-Forwarded-Proto`, `X-Forwarded-Host`, `Host`.
- Preserve explicit override:
  - If `APP_PUBLIC_URL` is set → always use it (prod lock).
- Refactor link builders:
  - Update `_action_url()` and `_landing_redirect()` in `transactions.py` to accept `Request` and compute base dynamically.

**Docs**
- Add `.env.example` notes:
  - `APP_PUBLIC_URL` should be set in prod; optional in preview/dev.

---

## 3) Next Actions (immediate)

### P0 — Wave 3 (now)
1. Implement listing-level `shipping_fee_cents` end-to-end.
2. Wire PayPal shipping-fee capture for donation claim when shipping fee > 0.
3. Transactions page polish: tabs + chips + confirm-receipt CTA.
4. APP_PUBLIC_URL: auto-derive when unset + explicit override.

### P1
5. Tighten swap reservation semantics:
   - reserved vs removed policy on accept
   - timeout/release logic for stale accepted swaps

### P2
6. Object storage migration (Mongo base64 bloat → R2/S3).
7. Phase O: Swap Stylist Brain to fine-tuned Gemma 4 E2B (blocked on fine-tuning + hosting).

### P3
8. Refactor `AddItem.jsx` into modules.

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

### Marketplace Wave 3 (target)
- Shipping fee:
  - ✅ `Listing.shipping_fee_cents` exists and is editable.
  - ✅ Sell PayPal charges include shipping.
  - ✅ Donate claim requires PayPal shipping payment only when shipping fee > 0.
  - ✅ UI nudges local pickup: “Meet locally to skip the fee 🌱”.
- Transactions UI:
  - ✅ Tabs + multi-select status chips.
  - ✅ Confirm receipt CTA appears appropriately.
- Environment URLs:
  - ✅ Email action links and redirects land on the correct environment when `APP_PUBLIC_URL` is unset.

---

## Out of scope for Wave 3 (deferred)
- Swap PayPal capture at propose-time (Wave 4+ if community requests it)
- Refund policy for captured donation shipping
- Transactions page search by listing title