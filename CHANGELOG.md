# Changelog

All notable changes to DressApp are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

Tags are applied with `git tag -a vX.Y.Z -m "..."` and pushed to `origin`.

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
