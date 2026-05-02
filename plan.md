# DressApp — Development Plan (Core-first) **UPDATED (Marketplace Wave 2: Swap + Donate + Email Landing + Listing Detail Enrichment)**

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

### 🎯 Marketplace Wave 2 — Swap + Donate pipelines (JWT-signed email actions) — **P0 / NOW**
Build the first complete “non-buy” marketplace transaction flows:
1. **Swap pipeline**: propose → email accept/deny (JWT-signed) → confirm receipt → complete.
2. **Donation pipeline**: claim donation → optional handling-fee PayPal payment → donor/recipient email confirmation.
3. **Transaction landing page**: a minimal page for accept/deny clicks from emails.
4. **Listing detail enrichment**: always show **size, description, condition** clearly.

**Decisions locked (user):**
- **JWT approach**: signed tokens using existing `JWT_SECRET` with **24h expiry** (recommended baseline; can be 7d if you prefer later).
- **Swap UX**: swap button opens a **modal** listing the user’s closet; user selects **1 offered item**.
- **Donation**: “Claim donation” with **optional handling-fee payment via PayPal**.
- **Landing page**: minimal status banner + listing summary + “Back to Marketplace” CTA.
- **Self actions**: hide Swap/Donate on own listings.

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

### Marketplace Wave 2 — Swap + Donate + Email landing **(P0 / IN PROGRESS)**

#### W2.0 — Goals + constraints (locked)
- Do not expose PII on public listing page.
- Email action links must be safe:
  - signed JWT using `JWT_SECRET`
  - dedicated `aud` claim for actions (avoid confusion with auth JWT)
  - short expiry (24h)
  - single-use protection using `jti` persisted/consumed.

---

#### W2.1 — Backend schema updates (transactions)
**File:** `app/backend/app/models/schemas.py`
- Add `Transaction.kind: "buy" | "swap" | "donate"` (default `"buy"` for backward compatibility).
- Add nested subdocuments:
  - `Transaction.swap`:
    - `offered_item_id: str`
    - `accepted_at: str | None`
    - `denied_at: str | None`
    - `lister_received_at: str | None`
    - `swapper_received_at: str | None`
    - `completed_at: str | None`
    - `action_token_jti: str | None` (or `accept_token_jti`, whichever naming you prefer)
  - `Transaction.donate`:
    - `handling_fee_cents: int | None`
    - `accepted_at: str | None`
    - `denied_at: str | None`
    - `completed_at: str | None`
    - `action_token_jti: str | None`
- Extend `TxStatus` safely if needed (or keep `pending/paid/...` and drive swap/donate state from nested timestamps). Prefer **minimal breaking changes**.

---

#### W2.2 — Backend service: JWT action tokens
**New file:** `app/backend/app/services/swap_tokens.py` (name can be generalized to `action_tokens.py`)
- `mint_action_token(*, tx_id: str, role: str, decision: str, expires_hours: int = 24) -> str`
  - JWT claims:
    - `aud="dressapp.tx_action"`
    - `sub=tx_id`
    - `role` (e.g., `"lister" | "swapper" | "donor" | "recipient"`)
    - `decision` (optional; or passed as URL param)
    - `jti` random UUID
    - `iat`, `exp`
- `verify_action_token(token: str) -> dict` validates signature, exp, aud.
- **Single-use enforcement**:
  - persist expected `jti` to the transaction on creation
  - on consumption, compare and then clear/rotate/mark-consumed.

---

#### W2.3 — Backend endpoints (Swap)
**File:** `app/backend/app/api/v1/transactions.py`
- `POST /api/v1/transactions/swap`
  - Auth required.
  - Body: `{ listing_id, offered_item_id }`
  - Validations:
    - listing exists and `status==active`
    - not swapping with self
    - offered closet item belongs to swapper
  - Creates transaction:
    - `kind="swap"`
    - `status="pending"` (or `"pending"` + nested state)
    - sets `swap.offered_item_id`
    - sets `swap.action_token_jti`
  - Sends `email_service.swap_request()` to the lister with accept/deny URLs.

- `GET /api/v1/transactions/action?token=...&decision=accept|deny`
  - **Public (no auth)**.
  - Verifies token + single-use.
  - Applies decision:
    - accept: sets `swap.accepted_at`, may move listing to `reserved`/`removed` (policy decision)
    - deny: sets `swap.denied_at`
  - Sends follow-up:
    - accept → `swap_success` to both
    - deny → `swap_denied` to swapper
  - Redirects to frontend landing:
    - `/transactions/{id}/landing?status=accepted|denied`.

- `POST /api/v1/transactions/{tx_id}/confirm-receipt`
  - Auth required.
  - Sets either `lister_received_at` or `swapper_received_at`.
  - If both confirmed:
    - set `swap.completed_at`
    - swap item ownership in `closet_items` (or duplicate into each closet; final policy)
    - retire/close marketplace listing(s).

**Testing (curl):**
- Propose swap, ensure tx created.
- Hit accept link; verify accepted.
- Hit accept again; verify rejected (token single-use).
- Confirm receipt as both parties; verify completion.

---

#### W2.4 — Backend endpoints (Donate)
**Files:** `app/backend/app/api/v1/transactions.py`, possibly `app/backend/app/api/v1/payments.py`
- `POST /api/v1/transactions/donate`
  - Auth required.
  - Body: `{ listing_id, handling_fee_cents?: int }`
  - Validations:
    - listing exists and mode is `donate`
    - not claiming own donation
  - If `handling_fee_cents > 0`:
    - create PayPal order (reuse PayPal create/capture patterns)
    - on capture: mark donation accepted + trigger `donation_both`.
  - If fee is 0:
    - create transaction and send donor email for accept/deny action (JWT).
- Reuse `donation_both()` template once accepted.

---

#### W2.5 — Frontend: ListingDetail enrichment + mode-aware CTAs
**File:** `app/frontend/src/pages/ListingDetail.jsx`
- Always show:
  - `size`
  - `condition`
  - `description`
- Render CTAs based on `listing.mode`:
  - `sell`: keep PayPal buy button
  - `swap`: show “Propose a swap” button
  - `donate`: show “Claim donation” (and optional fee)
- Hide swap/donate buttons when `isOwner === true`.

---

#### W2.6 — Frontend: Swap picker modal
**New file:** `app/frontend/src/components/SwapPickerModal.jsx`
- Shadcn `Dialog` + `ScrollArea`.
- Loads closet items (ideally a lightweight endpoint or paginated list).
- Single-select: choose 1 offered item.
- Submit calls `api.proposeSwap(listingId, offeredItemId)`.

**API client changes:** `app/frontend/src/lib/api.js`
- `proposeSwap(listingId, offeredItemId)` → `POST /transactions/swap`
- `proposeDonate(listingId, handlingFeeCents?)` → `POST /transactions/donate`
- `confirmReceipt(txId)` → `POST /transactions/:id/confirm-receipt`

---

#### W2.7 — Frontend: Transaction landing page
**New file:** `app/frontend/src/pages/TransactionLanding.jsx`
- Route: `/transactions/:id/landing`
- Loads minimal transaction + listing summary.
- Displays status banner based on `?status=` query:
  - accepted / denied / pending
- “Back to Marketplace” CTA.

**File:** `app/frontend/src/App.js`
- Add route entry for landing page.

---

#### W2.8 — Testing & release hygiene
- Manual backend testing with curl.
- Frontend manual testing + screenshots.
- Update `CHANGELOG.md` with Wave 2 entries.

---

## 3) Next Actions (immediate)

### P0 (now) — Marketplace Wave 2
1. Implement **Transaction schema** updates (`kind`, `swap`, `donate`).
2. Implement **JWT action token service** with `aud` + `jti` single-use enforcement.
3. Add **swap endpoints** (propose + public action + confirm receipt).
4. Add **donate endpoints**, including **optional PayPal handling-fee** flow.
5. Frontend:
   - ListingDetail: show size/condition/description; mode-aware CTAs; hide self actions.
   - Add SwapPickerModal.
   - Add TransactionLanding route/page.
6. End-to-end manual verification:
   - propose swap → accept/deny via emailed link → landing page.
   - receipt confirmations → completion.
   - donate claim → fee/no-fee path → email confirmations.

### P1
7. Tighten policies + UX
   - Decide listing reservation semantics on swap accepted (reserved vs removed).
   - Better surfacing in `/transactions` page (filter by kind/status).

### P2
8. Object storage migration (Mongo base64 bloat → R2/S3).

### P3
9. Refactor `AddItem.jsx` into modules.

---

## 4) Success Criteria

### Marketplace Wave 1 (already)
- ✅ Shared items auto-publish.
- ✅ Deleting closet item retires linked listing.
- ✅ Seller card shows only safe merchant info with correct fallback chain.
- ✅ Resend sale emails trigger on PayPal capture.

### Marketplace Wave 2
- Swap:
  - Users can propose a swap from listing detail.
  - Lister receives email with **JWT-signed** Accept / Decline.
  - Tokens expire and are single-use.
  - Accept/Decline redirects to `/transactions/:id/landing` with correct status.
  - Both parties can confirm receipt; swap completes and listings close.

- Donate:
  - Users can claim donation.
  - Optional handling-fee PayPal payment works.
  - Donor/recipient receive confirmation email (`donation_both`).

- UI:
  - Listing detail clearly shows **size, description, condition**.
  - Swap/Donate CTAs are hidden on own listings.
  - Landing page works even in logged-out browsers (email click).
