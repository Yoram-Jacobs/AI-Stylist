# DressApp — Development Plan (Core-first) **UPDATED (Eyes v3 / Gemma 4 E2B self-host LIVE on production VPS)**

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

### ✅ Phase O — Wave O.3 — Eyes v3 (Gemma 4 E2B) Self-Host on Hetzner VPS — **SHIPPED & LIVE**
**Primary objective achieved:** Custom LoRA-fine-tuned Gemma 4 E2B vision model now serves AddItem garment analysis in production, replacing the managed-API dependency for the Eyes tier. **Gemini 2.5 Flash remains the safety fallback**.

**Pipeline (Colab notebook `docs/Eyes_v2_Merge_Quantize.ipynb`):**
- ✅ Diagnosed architecture mismatch (Gemma **4** E2B, not Gemma 3n): uses `Gemma4ClippableLinear` wrappers, tied embeddings, PLE lookup tables.
- ✅ Rewrote merge pipeline with dynamic unwrap/rewrap of `Gemma4ClippableLinear` for PEFT compatibility.
- ✅ Fixed `pillow` + `torchao` dependency conflicts blocking the Colab build.
- ✅ Two-pass `llama.cpp` conversion (F16 mmproj first, then LM).
- ✅ Mixed-precision quantization:
  - Body: **Q4_K_M**
  - Tied embeddings: **Q8_0**
  - Norms: **F32**
  - Vision/audio projector (mmproj): **F16**
- ✅ Final footprint: **~4.85 GB** total (3.9 GB LM + 940 MB mmproj).
- ✅ Validated inference in Colab: ~15 s cold, accurate **18-field JSON** garment schema.

**Backend changes:**
- ✅ `parse_eyes_response` patched to handle both object and array responses from the model (multi-garment inputs).

**Production VPS cutover (Hetzner CX32, 7.6 GB RAM):**
- ✅ Confirmed VPS architecture: backend talks to a separate `dressapp-eyes` Docker container (`http://eyes:7860`) which proxies to `llama-server` on `:8080` reading from volume `eyes-cache` mounted at `/var/lib/docker/volumes/dressapp_eyes-cache/_data`.
- ✅ Uploaded GGUFs into the Docker volume:
  - `Eyes_v3_Gemma4_E2B-Q4_K_M.gguf`
  - `Eyes_v3_Gemma4_E2B-mmproj-F16.gguf`
- ✅ Updated `deploy/.env`:
  - `EYES_MODEL_FILE=Eyes_v3_Gemma4_E2B-Q4_K_M.gguf`
  - `EYES_MMPROJ_FILE=Eyes_v3_Gemma4_E2B-mmproj-F16.gguf`
- ✅ **Fixed compose wiring**: added `EYES_MODEL_FILE: ${EYES_MODEL_FILE:-}` to `deploy/docker-compose.yml` so the container receives the correct LM filename (previously only mmproj was plumbed; LM defaulted to baked-in `phase6-Q4_K_M.gguf`).
- ✅ Recreated service correctly using **service name** `eyes` (not container name):
  - `docker compose -f deploy/docker-compose.yml up -d --force-recreate eyes`

**Live verification (from `dressapp-eyes` logs):**
- ✅ `general.architecture: gemma4`, `general.name: Eyes_v3_Gemma4_E2B_merged`
- ✅ Quantization mix loaded as designed: f32:263 · f16:1 · q8_0:2 · q4_K:251 · q6_K:24
- ✅ Memory fit: projected ~**3735 MiB** host usage vs **7745 MiB** available → ~**4 GB headroom**
- ✅ mmproj loaded (`projector: gemma4v`, `vision=True`)
- ✅ `/healthz` returns **200 OK**; `Application startup complete`

**Bugs found & fixed during cutover:**
- 🐛 Compose confusion: attempted `docker compose ... dressapp-eyes` (container name) but compose expects **service name** (`eyes`).
- 🐛 Missing LM env plumbing: `EYES_MODEL_FILE` wasn’t passed through compose; resulted in stale baked-in LM default.

**Post-cutover follow-ups (open):**
- ⏳ Real garment-photo smoke test through the live app (<30 s response, 18-field JSON, no Gemini fallback).
- ⏳ Rotate exposed secrets from deployment transcript: `EYES_HF_TOKEN`, `EYES_API_TOKEN`, `GEMINI_API_KEY`, `GOOGLE_OAUTH_CLIENT_SECRET`.
- ✅ ~~Remove dead code: `app/backend/app/services/eyes_local_gemma4.py` + dormant `EYES_GEMMA_BACKEND=local` branch in `garment_vision.py`.~~ — **DONE** (deleted file; stripped routing branch from `garment_vision.py` and diagnostics block from `admin.py`; backend restarted clean, lint passes).
- ⏳ After 24 h stable traffic: delete deprecated GGUFs from VPS volume (`phase6-Q4_K_M.gguf`, `mmproj-Gemma4E2B-f16.gguf`).
- ⏳ **(VPS action) Update `dressapp-eyes` proxy `main.py`** to forward two new payload fields to `llama-server`:
  - `response_format` / `json_schema` → grammar-constrained decoding to the `EYES_JSON_SCHEMA` (`oneOf` single object | array).
  - `enable_thinking` / `think` (default `false` from backend) → per-request reasoning toggle, overriding the container's launch defaults. AddItem stays `false`; future Brain experiments can flip `true` per request.
  Backend already sends both fields; proxy currently ignores them harmlessly.
- ✅ ~~Live `_extract_json` in `garment_vision.py` only parses objects.~~ — **DONE**
- ✅ ~~Output language fix.~~ — **DONE**

### ✅ Phase L — Localization Wave 3 — Manual UI wiring patches — **SHIPPED**
Closed the last 4 known gaps where translated strings already existed in every locale JSON but the React code was still rendering raw English. Documented originally in `/app/docs/code_fixes_needed.md`.

- ✅ **ListingDetail.jsx (1a–1d)** — Listing chips now wire through existing taxonomy keys:
  - `category` → `taxonomy.categories.<value>`
  - `mode` (donate/swap) → `taxonomy.intent.<value>`
  - `condition` → `addItem.condition` label + `taxonomy.condition.<value>` value
  - `size` → `addItem.size` label (replacing the non-existent `market.sizeLabel` key)
- ✅ **Home.jsx (2a–2b)** — Trend-Scout chip + fallback cards:
  - Added `trends.bucket.<slug>` block to all 12 locales (7 buckets: `ss26-runway`, `street`, `sustainability`, `influencers`, `second_hand`, `recycling`, `news_flash`).
  - Chip now prefers the localised bucket label and falls back to the raw backend `card.label`.
  - `FALLBACK_TRENDS` constant moved inside the component as a `useMemo` keyed on `i18n.language`; cards read from `home.fallbackTrends.fb1/2/3.{label,headline,summary}` in every locale.
- ✅ **SeoBase.jsx (3)** — `META` constant refactored to i18n keys:
  - Added `seo.routes.<key>.{title,description}` block (13 routes) to all 12 locales.
  - `<html lang>` now reflects the active `i18n.language` (was hard-coded `"en"`).
  - Page title + meta description + OG/Twitter tags now switch language alongside the UI; verified via Playwright (zh: title `登录 | DressApp`, `html.lang="zh"`, and react-helmet emits the localised description).
- ✅ **countries.js (4)** — Adopted `Intl.DisplayNames`:
  - Added shared `localisedCountryName(code, lang, fallback)` helper.
  - `CountryCombobox` refactored to consume the helper (no more inline `new Intl.DisplayNames(...)`).
  - Bundled English `name` field retained as a safety fallback for browsers without region tables and for `resolveCountry()` free-text matching.

**Known pre-existing gap (out of scope here, flagged for later):**
- `public/index.html` ships a static `<meta name="description">` that react-helmet does not remove. The helmet still emits the correct localised tag, but the static one remains as `<meta>[0]`. Most crawlers respect the last tag, but a future pass should drop the static one (or move it behind a build-time template) for cleaner HTML.

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
- ✅ Verified via frontend testing agent (`iteration_19`).

### ✅ Phase X — Chrome Extension (Shopping Assistant) — **SHIPPED IN REPO (manual Chrome E2E pending; backend verified)**
**Primary objective achieved:** A Manifest V3 Chrome extension exists end-to-end (popup UI, content scripts, site adapters, auth handoff, background service worker, backend endpoint, and a production `dist/` build).

**What shipped (X.0–X.3)**
- ✅ Extension scaffold + architecture (React + Vite + MV3, CRXJS bundling)
- ✅ Popup UI (DressApp-themed Tailwind):
  - loading / disconnected / connected / error states
  - Connect flow opens `https://<backend>/extension/connect?ext_id=<id>&v=1`
  - displays `/api/v1/users/me` measurement summary
  - sign-out wipes token in `chrome.storage.local`
- ✅ Content script injection on supported stores:
  - mounts a “DressApp size” button next to detected size anchors
  - extracts size chart HTML and calls backend analysis
  - renders an in-page overlay tooltip with the recommendation
- ✅ Store adapters present for: **Zara, ASOS, Shein, H&M, Amazon, AliExpress** (+ generic fallback)
- ✅ Secure token handoff page shipped in web app:
  - `frontend/src/pages/ExtensionConnect.jsx`
  - extension receives `{type:'DRESSAPP_EXT_TOKEN', token, backend, user}`
  - content-script `auth-bridge.js` forwards handoff to SW
- ✅ Service worker provides single-source-of-truth auth + API calls:
  - caches `/users/me` for popup responsiveness
  - isolates bearer token from content/popup scripts
- ✅ Manifest, icons, and `dist/` build:
  - icons present in `/app/chrome-extension/icons/`
  - `yarn build` produces `/app/chrome-extension/dist/` and valid manifest rewrites

**Backend integration (verified)**
- ✅ `POST /api/v1/sizes/analyze-chart` exists and is routed
- ✅ Unauthenticated requests return **401**
- ✅ Authed behavior verified by automated testing agent (`iteration_20.json`): **9/9 tests passed**

**Backend stability fixes performed during Phase X**
- ✅ `HFImageService` now tolerates older `huggingface_hub` clients (no `provider` kwarg)
- ✅ `sizes.py` provider activity tracking fixed:
  - corrected import path (`from app.services import provider_activity`)
  - corrected call signature to `provider_activity.record(provider, ...)`

**✅ Phase X.5 — Extension hardening (modal/image charts + screenshot fallback + testability) — SHIPPED**
- ✅ Image-based chart detection (`detectChartImage`) for charts rendered as single images inside modals/sections.
- ✅ Screenshot fallback when HTML/image extraction fails:
  - added SW handler `CAPTURE_VISIBLE_TAB` using `chrome.tabs.captureVisibleTab`
  - added `tabs` permission to manifest
  - content script now sends `chart_screenshot_b64` (JPEG base64, no prefix) to backend
- ✅ Broader anchor detection:
  - supports size pill/button groups and accessibility roles
- ✅ Overlay UX + testability:
  - retry CTA and stable `data-testid` selectors on overlay elements

**Known limitations / pending**
- ⏳ Manual E2E testing inside Chrome (load unpacked, validate connect + overlay + chart scraping on real product pages)
- ⏳ Chrome Web Store publishing (deferred)

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

#### W3A — Listing-level Shipping Fee + PayPal hookup — **SHIPPED**
- ✅ **Schema:** `Listing.shipping_fee_cents: int = 0` (default 0)
- ✅ **DTOs:** added to `CreateListingIn` + `UpdateListingIn`
- ✅ **SELL flow (PayPal):** amount includes shipping; returns breakdown.
- ✅ **DONATE flow:** PayPal capture only when shipping_fee > 0; otherwise email-only.
- ✅ Compatibility: `handling_fee_cents` retained but ignored.

#### W3B — Transactions Page Polish — **SHIPPED**
- ✅ Tabs by kind with counts.
- ✅ Multi-select status chips.
- ✅ Inline confirm receipt CTA for accepted swap/donate.

#### W3C — APP_PUBLIC_URL Hygiene — **SHIPPED**
- ✅ Auto-derive base URL when unset via forwarded headers.
- ✅ Respect explicit override for prod lock.
- ✅ Refactor link builders to accept `Request`.

---

### Marketplace Stability Hotfix (v1.1.2 candidate) — **SHIPPED**
Out-of-band hotfix wave for “items stuck on Private / can't delete listing” regressions.

---

### SPA eager-load caching (Closet + Marketplace + Experts) — **SHIPPED & VERIFIED**
Delivered previously; unchanged.

---

### Phase O — Stylist Provider Migration (Gemini → Qwen → Gemma) — **IN PROGRESS**

#### Wave O.1 — Stylist Brain swap to Qwen-VL-Max-Latest — **SHIPPED (v1.1.1 candidate)**
Delivered previously; unchanged.

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
- Backend-only validation + targeted integration tests.

#### Wave O.3 — Eyes v3 (Gemma 4 E2B) self-host cutover — **SHIPPED & LIVE**
See Objectives section above.

#### Wave O.4 — Add Gemma4-E4B fine-tune into provider chain — **LATER (blocked on hosting)**
- Host the fine-tuned Gemma4-E4B on a 24/7 inference platform (HF Inference Endpoints / Modal / Runpod).
- Add `GemmaStylistBrain` implementation and set:
  - `STYLIST_PROVIDER=gemma`
  - `STYLIST_FALLBACK=qwen`

---

### Phase X — Chrome Extension (Shopping Assistant) — **SHIPPED IN REPO / E2E PENDING**

#### X.0 — Repository layout (shipped)
Delivered previously; unchanged.

#### X.1 — Auth handshake (shipped)
Delivered previously; unchanged.

#### X.2 — Backend endpoint (shipped + verified)
Delivered previously; unchanged.

#### X.3 — Build & packaging (shipped)
Delivered previously; unchanged.

#### X.5 — Hardening for real-world store DOMs (shipped)
Delivered previously; unchanged.

#### X.6 — Pending validation & release (next)
- ⏳ Manual Chrome E2E:
  - Load unpacked from `/app/chrome-extension/dist`
  - Connect via popup → verify token stored → `/users/me` loads
  - Validate: button injection → chart detection (HTML/image/screenshot) → overlay recommendation
- ⏳ Publish to Chrome Web Store (deferred)

---

## 3) Next Actions (immediate)

### P0 — Next wave candidates
1. **Phase X.6 E2E (Chrome):** manual validation of connect + overlay + chart extraction on each store.
2. **Wave O.2:** migrate `garment_vision` Eyes + Brain from Gemini to Qwen-VL (high risk; AddItem pipeline).
3. Swap reservation semantics hardening:
   - reserved vs removed policy on accept
   - timeout/release logic for stale accepted swaps

### P1
4. Extension quality improvements (post-E2E):
   - add optional “Select chart area” interaction if needed for very custom charts
   - adapter selector tuning for store DOM changes
   - tighten origin allow-lists for production (extension id allow-list + externally_connectable)
5. Transactions page quality-of-life:
   - search by listing title
   - per-kind empty states and summaries

### P2
6. Object storage migration (Mongo base64 bloat → R2/S3).
7. ✅ ~~Wave O.3: add fine-tuned Gemma4-E4B once 24/7 hosting is ready.~~ — **SHIPPED** as self-hosted Gemma 4 E2B in `dressapp-eyes` container.
8. Chrome Web Store publishing (deferred until Phase X.6 manual E2E passes).
9. **Eyes v3 post-cutover cleanup:**
   - ⏳ rotate exposed secrets (`EYES_HF_TOKEN`, `EYES_API_TOKEN`, `GEMINI_API_KEY`, `GOOGLE_OAUTH_CLIENT_SECRET`)
   - ✅ ~~remove dead `eyes_local_gemma4.py` + dormant `EYES_GEMMA_BACKEND=local` branch from `garment_vision.py`~~ — **DONE** (also stripped admin diagnostics block; backend restarted clean)
   - ⏳ delete deprecated GGUFs from VPS volume after 24 h stable traffic
   - (optional) add a short `deploy/README.md` note: service name is `eyes`, container is `dressapp-eyes`, and both `EYES_MODEL_FILE` + `EYES_MMPROJ_FILE` must be plumbed
10. Profile "Save changes" button always-active fix (`ProfileDetailsCard.jsx`) — track form dirtiness against loaded snapshot.

### P3
11. Refactor `AddItem.jsx` into modules.
12. ✅ ~~Live `_extract_json` is object-only.~~ — **DONE** Extended to handle arrays; `_coerce_single_garment()` collapses to first item for single-dict contract.
13. (orphan) `_hf_chat_json` in `garment_vision.py` is defined but never called — safe to delete in a future cleanup pass.

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
  - Donations remain free.
- ✅ Transactions UI:
  - Tabs + multi-select status chips.
  - Confirm receipt CTA appears appropriately for accepted swap/donate rows.
- ✅ Environment URLs:
  - Email action links and redirects land on the correct environment when `APP_PUBLIC_URL` is unset.
  - Explicit `APP_PUBLIC_URL` overrides derivation.

### SPA eager-load caching (Closet + Marketplace + Experts)
- ✅ App boot prewarms Closet, Marketplace (browse + my listings), and Experts.
- ✅ Returning to `/closet`, `/market`, `/experts` shows cached results immediately.
- ✅ Mutations properly invalidate/update caches.
- ✅ Verified via frontend testing agent `iteration_19`.

### Phase O — Stylist provider migration
- ✅ Wave O.1:
  - `/api/v1/stylist` uses Qwen-VL-Max-Latest by default.
  - Gemini remains available as fallback.
  - Provider selection controlled by env vars.
- ⏳ Wave O.2:
  - AddItem pipeline (`garment_vision`) produces the same closet item cards using Qwen.
- ✅ Wave O.3:
  - Self-hosted Gemma 4 E2B (custom LoRA, mixed-precision GGUF) live in `dressapp-eyes` container on Hetzner VPS.
  - 18-field JSON schema validated in Colab; live container boot + healthcheck green.

### Phase X — Chrome Extension (Shopping Assistant)
- ✅ Build artifacts exist and backend endpoint verified by tests.
- ✅ Hardening shipped for image-based charts + screenshot fallback.
- ⏳ Manual E2E in Chrome passes (connect + injection + overlay on each supported store).

---

## Out of scope (deferred)
- Swap PayPal capture at propose-time (Wave 4+ if community requests it)
- Refund policy for captured donation shipping
- Transactions search by listing title (future QoL)
- Chrome Web Store publishing (until Phase X.6 manual E2E is complete)
