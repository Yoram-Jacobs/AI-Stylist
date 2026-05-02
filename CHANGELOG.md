# Changelog

All notable changes to DressApp are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

Tags are applied with `git tag -a vX.Y.Z -m "..."` and pushed to `origin`.

---

## [Unreleased] — Marketplace Wave 2

### Added
- **Swap pipeline**. Users can propose a swap directly from a listing:
  - New `POST /api/v1/transactions/swap` creates a zero-cash transaction
    linking the swapper's offered closet item to the lister's listing.
  - `SwapPickerModal` frontend component (Shadcn Dialog) lets the user
    browse their own closet and pick one item to offer.
- **Donation flow**. New `POST /api/v1/transactions/donate` endpoint plus
  one-click "Claim this donation" CTA on `mode=donate` listings. Handling
  fee is sent to the backend as metadata; PayPal handling-fee capture is
  deferred to a follow-up iteration.
- **JWT-signed email accept/deny**. New `services/action_tokens.py` mints
  short-lived JWTs (7-day expiry) with a dedicated `aud="dressapp.tx_action"`
  claim so they cannot be replayed against auth endpoints. Each token
  carries a random `jti` that is persisted on the transaction and spent
  exactly once — reuse and tampering both fail gracefully.
- **Public action endpoint** `GET /api/v1/transactions/action?token=…&decision=…`
  verifies the JWT, applies accept/deny idempotently, fires follow-up
  emails (`swap_success` / `swap_denied` / `donation_both`), and 303-
  redirects the browser to the transaction landing page.
- **Transaction landing page** at `/transactions/:id/landing` (auth-optional
  so email clicks from logged-out browsers still work). Renders a status
  banner (Accepted / Declined / Pending / Expired), listing summary with
  size + condition + description, and a Back-to-Marketplace CTA. Backed
  by a minimal public projection via `GET /transactions/:id/landing-summary`.
- **Confirm-receipt endpoint** `POST /api/v1/transactions/:id/confirm-receipt`.
  Both parties can mark the incoming item as received; when both have
  confirmed, the swap completes, closet ownership flips, and listings
  close.
- **Listing detail enrichment** on `/market/:id`:
  - Always-visible badges for Size, Condition, Category, and Mode.
  - Always-visible Description block.
  - Mode-aware primary CTA — Buy / Swap / Donate — with self-swap and
    self-donate hidden when the listing is owned by the viewer.

### Changed
- `Transaction` schema gained a `kind` discriminator ("buy" | "swap" |
  "donate") plus nested `swap` and `donate` sub-documents. Legacy `buy`
  transactions are untouched (default remains `kind="buy"`).
- `TxStatus` literal extended with `accepted`, `denied`, `shipped`,
  `completed` — drives the new swap + donate state machine without
  breaking reads of older buy ledger rows.
- `transactions.paypal.order_id` index migrated from `sparse=True` (which
  still indexes explicit nulls) to a `partialFilterExpression` that only
  covers string values. Prevents duplicate-key 500s when swap/donate
  transactions — which never touch PayPal — insert with a null
  `paypal.order_id`.

### API / endpoints added
- `POST /api/v1/transactions/swap`
- `POST /api/v1/transactions/donate`
- `GET  /api/v1/transactions/action`
- `POST /api/v1/transactions/:id/confirm-receipt`
- `GET  /api/v1/transactions/:id/landing-summary` (public)

### Frontend api.js additions
- `api.proposeSwap(listingId, offeredItemId)`
- `api.claimDonation(listingId, handlingFeeCents)`
- `api.confirmReceipt(txId)`
- `api.getLandingSummary(txId)` (unauthenticated)

---

## [v1.0-stable] — 2026-05-01

First stable milestone shipped to production (https://dressapp.co) on Hetzner
with Atlas M10. Contest-ready build.

### Added
- **Phase Z2 — Pre-flight duplicate detection**. Client computes SHA-256 +
  perceptual (aHash) hashes in-browser on file select. `POST /closet/preflight`
  returns matches against the user's closet BEFORE any SegFormer / rembg /
  Gemini analyze cost is paid. Users can skip duplicates or explicitly
  "Add anyway" (red ⭐ overlay on card).
- **Star auto-demotion on delete**. When a closet item is deleted, the
  remaining fingerprint group is inspected; if only starred copies survive,
  the oldest is promoted back to "original" (`is_duplicate=false`).
- **DressApp logo lockup**. Full favicon set (16/32/48/180/192/512 + `.ico`),
  PWA manifest icons, Apple touch icon. New shared `<BrandLogo>` component
  placed in the login editorial panel, login mobile header, and TopNav.
- **Search bar polish** on Closet:
  - Debounced live-search (~300 ms) for keyword mode — no need to hit Enter.
  - Clear (X) button inside the search input when the field has text.
  - Active-state accent ring on Category / Source selects when their value
    is non-default.
- **Category filter synonym map** — backend `list_items` now matches
  `shoes ↔ Footwear`, `accessory ↔ Accessories`, `dress ↔ Full Body`,
  `top ↔ Top/tops`, etc., case-insensitively. Fixes long-standing bug where
  filters returned 0 items because legacy rows used different labels.
- **Verification markers** on `GET /api/v1/closet/analyze/version`:
  `preflight_duplicate_v1`, `legacy_post_analyze_dup_removed`,
  `category_synonyms_v1` — all return `true` when the correct build is
  deployed.

### Changed
- **Stylist Brain** (`outfit_composer.py`, `stylist_memory.py`) now excludes
  `is_duplicate=true` items from outfit suggestions.
- **`/closet/analyze`** no longer invokes `find_potential_duplicate`. The
  post-analysis attribute matcher is permanently disabled — pre-flight is
  now the sole duplicate gate. The response field `potential_duplicate` is
  always `null` (kept for back-compat with older frontend bundles).

### Fixed
- **Production deploy unblocked**: `protobuf==7.34.1 → 5.29.6` in
  `backend/requirements.txt` to resolve `grpcio-status <6.0dev` conflict
  that was failing fresh Docker builds on Hetzner.
- **Atlas quota crisis recovery** — identified 509 MB of `segmented_image_url`
  data URLs inflating MongoDB past the M0 512 MB ceiling; upgraded to M10
  (10 GB) to restore writes. (Object-storage migration still pending — see
  roadmap.)
- Hetzner `Dockerfile.backend` now passes `--extra-index-url` for
  `emergentintegrations` during pip install.

### Infrastructure
- **Preview pod DB name**: `backend/.env` set to `DB_NAME="test_database"` so
  the dev user's 113-item closet is reachable on the preview pod. Production
  Atlas `.env` is unaffected (`DB_NAME="dressapp"`).

### Known issues / deferred
- ~500 MB of inline base64 image data still sits in Atlas `closet_items`.
  M10 tier provides comfortable headroom; proper migration to object storage
  (Cloudflare R2 or Emergent integration) is deferred to v1.1.
- `AddItem.jsx` is > 1800 lines and overdue for refactor (tracked for v1.2+).

---

## [Unreleased]

Work staged for v1.1.x (none yet — next feature branch starts here).
