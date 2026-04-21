# DressApp — Development Plan (Core-first) **UPDATED (post Phase A architecture pivot)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated & stabilised** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference (free tier) using **`mattmdjaga/segformer_b2_clothes`**.
  - **Image generate/edit**: Hugging Face **FLUX.1-schnell**.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, integration-tested.
- ✅ **Phase 4 shipped**: Google Calendar OAuth + Trend‑Scout autonomous agent.
- ✅ **Phase 5 shipped**: Admin dashboard, provider activity monitoring, accessibility + SEO hardening.
- ✅ **Add Item overhaul shipped**: batch upload + animated scanning + "The Eyes" auto-fill + rich closet schema + one‑click auto‑listing.
- ✅ **Multi-Item Outfit Extraction shipped**: one uploaded photo → N editable item cards with IoU-NMS dedupe + "already cropped" short-circuit.
- ✅ **Closet Bulk Delete shipped**: multi-select mode on `/closet` with confirmation dialog + parallel deletes.
- ✅ **Phase A (architecture pivot) shipped (NEW)**: provider-dispatched Eyes (Gemini default, Gemma HF path ready for user's fine-tune), local FashionCLIP embedding service + `/closet/search`, native camera capture on Add Item.
- 🎯 **Next milestone**: PayPlus payments integration — *deferred until API credentials are available*.

> **Operational note:** EMERGENT_LLM_KEY budget is topped up with auto‑recharge. Text/multimodal calls (Stylist + The Eyes + Trend‑Scout) are expected to be stable, but transient upstream 503s may still occur (handled gracefully).

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
- ✅ `/app/scripts/poc_stylist_pipeline.py` (reflects HF segmentation + HF FLUX image variant generation)

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
**User stories (Phase 2)**
1. ✅ CRUD closet items with `source=Private|Shared|Retail`.
2. ✅ Upload item photo via URL or base64 (**best‑effort segmentation**).
3. ✅ Authenticated stylist grounded in closet + weather + session history.
4. ✅ Public marketplace browse (filters) + seller-owned listing CRUD.
5. ✅ Transaction ledger creation with **7% platform fee after processing fee math** (payments wiring deferred).

**Phase 2 delivered (authoritative file list; updated for vision + rich schema)**
- ✅ Auth & security
  - `/app/backend/app/services/auth.py`
  - `/app/backend/app/api/v1/auth.py`
  - `/app/memory/test_credentials.md`

- ✅ User profile
  - `/app/backend/app/api/v1/users.py`

- ✅ Closet
  - `/app/backend/app/api/v1/closet.py`
    - best‑effort segmentation via HF segmentation service
    - `/closet/{id}/edit-image` uses **HF FLUX** variant generation
    - ✅ `POST /closet/analyze` (The Eyes)
    - ✅ `POST /closet` extended for rich fields + auto-listing
  - `/app/backend/app/services/hf_segmentation.py`
  - `/app/backend/app/services/hf_image_service.py`
  - ✅ `/app/backend/app/services/garment_vision.py` (The Eyes)

- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`

- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py` (uses `hf_image_service` for optional infill)
  - `/app/backend/app/api/v1/stylist.py`
  - `/app/backend/app/services/gemini_stylist.py`

- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py`

**Phase 2 known limitations (expected, not bugs)**
- Payments are not wired (transactions remain `pending`).

---

### Phase 3 — Frontend V1 (React) **(COMPLETE + Add Item upgraded)**
**User stories (Phase 3)**
1. ✅ Register/login + one-tap dev login.
2. ✅ Add and manage closet items.
3. ✅ Stylist chat:
   - ✅ Image + text
   - ✅ Image + voice capture → transcript + advice
   - ✅ Audio playback for `tts_audio_base64`
4. ✅ Browse marketplace listings + fee/net breakdown.
5. ✅ Create/manage listings from closet items.
6. ✅ View ledger/transactions.

**Phase 3 delivered**
- ✅ All pages compile and routes are valid.
- ✅ `/transactions` page
  - `/app/frontend/src/pages/Transactions.jsx`
  - Routed in `/app/frontend/src/App.js`
  - Linked via TopNav dropdown

---

### Phase 4 — Context + Autonomy + Payments (PayPlus) **(PARTIALLY COMPLETE / PAYPLUS DEFERRED)**

#### Phase 4 (Part 1) — Google Calendar OAuth (P0) **(COMPLETE)**
**Delivered**
- ✅ Backend OAuth + Calendar API
  - `/app/backend/app/services/calendar_service.py`
  - `/app/backend/app/api/v1/google_auth.py`
  - `/app/backend/app/api/v1/stylist.py` real-event hydration when connected
- ✅ Frontend UI
  - `/app/frontend/src/components/CalendarConnect.jsx`
  - `/app/frontend/src/pages/Profile.jsx`
  - `/app/frontend/src/pages/Stylist.jsx` (badge + occasion fallback)

#### Phase 4 (Part 2) — Trend‑Scout Background Agent (P1) **(COMPLETE)**
**Delivered**
- ✅ Backend Trend‑Scout agent + persistence
  - `/app/backend/app/services/trend_scout.py`
  - `/app/backend/app/services/scheduler.py`
  - `/app/backend/app/api/v1/trends.py`
  - `/app/backend/app/db/database.py` unique `(bucket, date)` index
- ✅ Frontend Home feed integration
  - `/app/frontend/src/pages/Home.jsx` reads `/api/v1/trends/latest`
  - `/app/frontend/src/lib/api.js` includes `trendsLatest()`

#### Phase 4 (Part 3) — PayPlus Payments (replaces Stripe) **(NEXT / DEFERRED)**
**User stories**
1. Seller onboarding / payout routing using PayPlus (depends on PayPlus capabilities).
2. Buyer checkout creates a PayPlus payment session.
3. Webhooks update transaction lifecycle: `pending → paid/failed/refunded`.
4. Ledger consistency: store `gross`, `processing_fee`, `platform_fee (7% after fee)`, `seller_net`.

**Implementation (when PayPlus API credentials are available)**
- Confirm required credentials + environments (sandbox vs production)
- Define payout model: direct / escrow / split payout
- Backend endpoints:
  - create checkout/payment session
  - webhook handler
  - seller onboarding status endpoint (if applicable)
- DB refactor:
  - `users.stripe_account_id` → PayPlus equivalent
  - `transactions.stripe.*` → `transactions.payplus.*`
  - keep fee math unchanged

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
**User stories (Phase 5)**
1. ✅ Admin dashboard: revenue, users, marketplace activity, stylist usage.
2. ✅ Monitoring for external providers (latency + error rate + last error tail).
3. ✅ Trend‑Scout monitoring + manual force-run.
4. ✅ Accessibility hardening pass.
5. ✅ SEO hardening pass.

**Phase 5 delivered**
- ✅ Admin Dashboard backend (gated by `require_admin`)
  - `/app/backend/app/api/v1/admin.py`
    - `/admin/overview`
    - `/admin/users` + `/{id}/promote|demote`
    - `/admin/listings` + `/{id}/status`
    - `/admin/transactions`
    - `/admin/providers` + `/{provider}/calls`
    - `/admin/trend-scout` + `/run`
    - `/admin/llm-usage` (best-effort, never 500)
    - `/admin/system` (redacted config + key presence)

- ✅ Provider activity tracker
  - `/app/backend/app/services/provider_activity.py`
  - wired into:
    - HF image gen (`hf-image`)
    - HF segmentation (`hf-segformer`)
    - Gemini stylist (`gemini-stylist`)
    - Groq Whisper (`groq-whisper`)
    - Deepgram TTS (`deepgram-tts`)
    - OpenWeather (`openweather`)
    - ✅ The Eyes garment analyzer (`garment-vision`)

- ✅ Admin Dashboard UI
  - `/app/frontend/src/pages/Admin.jsx` (7 tabs: Overview/Providers/Trend‑Scout/Users/Listings/Transactions/System)
  - `/app/frontend/src/App.js` route: `/admin`
  - `/app/frontend/src/components/TopNav.jsx` adds “Admin” menu item for admin users only

- ✅ Accessibility
  - Skip link on first Tab (in App shell)
  - `<main id="main-content" tabIndex={-1}>` in `AppLayout`
  - Global `:focus-visible` outline
  - `prefers-reduced-motion` support
  - `aria-label` on icon-only nav elements

- ✅ SEO
  - `react-helmet-async` + per-route SEO
    - `/app/frontend/src/components/SeoBase.jsx`
    - `/app/frontend/src/App.js` wires `HelmetProvider` + `SeoBase`
  - Static assets:
    - `/app/frontend/public/robots.txt`
    - `/app/frontend/public/sitemap.xml`
    - `/app/frontend/public/manifest.json`

**Phase 5 testing**
- ✅ Comprehensive testing: `/app/test_reports/iteration_5.json`

---

### Add Item Overhaul — Batch Upload + The Eyes + Auto‑Listing **(COMPLETE)**
This feature spans Phases 2–3 (schema + backend + frontend UX) but is tracked separately because it materially upgrades the closet ingestion workflow.

**User stories**
1. ✅ User selects one or many images.
2. ✅ Each image is previewed immediately.
3. ✅ Animated “scanning” progress while The Eyes runs.
4. ✅ Auto-fill all fields, including structured composition arrays.
5. ✅ User can edit fields, set marketplace intent, then **Save All**.
6. ✅ If intent is `for_sale/donate/swap`, the item is auto-listed in one click.

**Delivered**
- ✅ Rich closet schema
  - `/app/backend/app/models/schemas.py`
    - `WeightedTag` model
    - extended `ClosetItem` fields:
      - name/title/caption
      - category/sub_category/item_type
      - brand
      - fabric_materials[{name,pct}], colors[{name,pct}]
      - pattern, gender, dress_code, season, tradition
      - state, condition, quality, size
      - price_cents, marketplace_intent, repair_advice, tags
      - listing_id back-reference

- ✅ The Eyes analyzer (Gemini 2.5 Pro multimodal)
  - `/app/backend/app/services/garment_vision.py`
  - `POST /api/v1/closet/analyze`
    - accepts `image_base64` OR `image_url`
    - strict JSON contract
    - emits provider activity: `garment-vision`
    - includes server-side `setdefault(...)` fallbacks for occasional missing fields
  - Swappable later to fine-tuned **Gemma 4 E4B** via env:
    - `GARMENT_VISION_PROVIDER`
    - `GARMENT_VISION_MODEL`

- ✅ Extended closet create with auto-listing
  - `POST /api/v1/closet` accepts all new fields
  - If `marketplace_intent in {for_sale,donate,swap}`:
    - creates closet item **and** creates active Listing
    - sets `closet_items.source = Shared`
    - sets `closet_items.listing_id`
    - stores 7% fee metadata (`FinancialMetadata.estimated_seller_net_cents`)

- ✅ Frontend batch upload + editing UX
  - `/app/frontend/src/pages/AddItem.jsx`
    - multi-file upload (`multiple`)
    - **parallel** analysis of all images
    - editable cards for every field
    - marketplace intent selector:
      - Own (default)
      - For Sale (shows price + live fee preview)
      - Donate / Swap
    - Save All → creates items (and listings when relevant) → toast → navigate to /closet

- ✅ Scanning animation
  - `/app/frontend/src/index.css` includes `.scanning` + keyframes `scan-line`, `scan-shimmer`, `scan-pulse`
  - disabled automatically under `prefers-reduced-motion`

**Testing**
- ✅ Add Item overhaul test pass: `/app/test_reports/iteration_6.json`
  - Backend: **89.9%**, Frontend: **100%**, Overall: **95%**
  - 0 critical bugs / UI bugs / integration issues

---

### Multi-Item Outfit Extraction — One photo → N cards **(COMPLETE)**
Upgrades "The Eyes" so a single uploaded outfit photo expands into a dedicated editable card for every garment, accessory, and piece of jewelry visible in the frame.

**User stories**
1. ✅ User uploads one outfit photo containing multiple pieces.
2. ✅ The Eyes detects every item (Gemini bounding-box detector).
3. ✅ Backend crops each bbox server-side (Pillow), drops tiny / full-frame detections.
4. ✅ Each crop is re-analysed in parallel for the rich 17-field form payload.
5. ✅ Frontend replaces the single upload card with `N` editable cards — each with its own tight crop, "Detected" badge, auto-filled fields, and independent marketplace intent.
6. ✅ Graceful fallback to single-item analysis when detection fails / yields nothing useful.

**Delivered**
- ✅ Backend orchestration
  - `/app/backend/app/services/garment_vision.py`
    - `detect_items()` — Gemini 2.5 Flash bounding-box detector (normalised 0–1000 coords, Gemini `[ymin, xmin, ymax, xmax]` order)
    - `_crop_to_bbox()` — Pillow cropper with ~4% padding + min-area filter
    - `analyze_outfit()` — full pipeline: detect → crop (thread pool) → parallel `analyze()` (semaphore=6) → returns `list[{label, kind, bbox, crop_base64, crop_mime, analysis}]`
    - parametrised `analyze(model=...)` so the per-crop path can use Flash for speed
  - `/app/backend/app/api/v1/closet.py`
    - `POST /closet/analyze` now accepts `multi: bool = True` and returns `{items: [...], count, ...legacyMirror}`
    - Safe Pydantic validation + defaulting per item (`_safe_analysis`)
    - Top-level fields mirror `items[0].analysis` for full backwards compatibility
  - `/app/backend/app/config.py`
    - `GARMENT_VISION_CROP_MODEL` (default `gemini-2.5-flash`) and `GARMENT_VISION_MAX_ITEMS` (default 6)
    - Keeps Pro as the default for single-image analysis while holding the multi-item pipeline under the 60s ingress budget

- ✅ Frontend expansion logic
  - `/app/frontend/src/pages/AddItem.jsx`
    - `analyzeCard()` reads the new `items` array; when >1 it replaces the single scanning card with `N` fresh cards, each owning its own crop as `base64` (so Save persists only the relevant garment)
    - Each expanded card keeps its own `mime`, `label`, hydrated fields, and marketplace intent
    - "Detected" badge overlay renders the Gemini label (e.g. *"shirt dress"*, *"sunglasses"*, *"dangle earring"*)
    - Toast confirms *"Detected N items in that photo — review each card below."*
    - `buildCreatePayload()` uses `card.mime` so expanded cards (no `File`) still save correctly

**Performance**
- Typical real outfit photo: **~25–35 s** total (≈10 s detection on Flash + ≈18 s per-crop Flash analysis in parallel batches of 6).
- Hard cap `max_items=6` prevents runaway cost on catalog-style photos.

**Testing**
- ✅ Multi-item extraction test pass: `/app/test_reports/iteration_7.json`
  - Backend **95%** (0 critical bugs, 0 flaky endpoints)
  - Verified: multi=true array shape, multi=false legacy path, 401 auth, 400 bad base64, regression suite (closet / stylist / market / admin)
  - Manually verified end-to-end in the browser: 1 Unsplash outfit portrait → **3 cards** rendered in 32 s, each with its own crop + label badge + complete auto-fill payload

**Key extension points**
- `GARMENT_VISION_CROP_MODEL` env var — swap to fine-tuned Gemma 4 E4B when the user's fine-tune is ready.
- `GARMENT_VISION_MAX_ITEMS` env var — raise the per-photo cap if future UX calls for it.

---

**Testing (legacy)**

---

### Phase A — Architecture pivot toward Gemma-on-edge **(COMPLETE)**
Lays the groundwork for the user's fine-tuned Gemma 4 E2B (Eyes) / E4B (Brain) edge deployment. No user-visible regressions — the default Eyes provider is still Gemini while Gemma HF routing stabilises and the fine-tune lands.

**Delivered**
- ✅ Provider-dispatched analyser in `garment_vision.py`
  - New `_hf_chat_json()` helper for any HF-hosted multimodal chat model (system prompt folded into first user message to satisfy Featherless / strict alternation rules).
  - `analyze(image, model=..., provider=...)` routes to either `hf` or `gemini` based on `GARMENT_VISION_PROVIDER`.
  - Service no longer hard-requires `EMERGENT_LLM_KEY`; it fails fast only on the configured provider's missing credential.
- ✅ Config surface in `app/config.py`: `GARMENT_VISION_PROVIDER`, `GARMENT_VISION_MODEL`, `GARMENT_VISION_CROP_MODEL`, `GARMENT_VISION_DETECT_PROVIDER`, `GARMENT_VISION_DETECT_MODEL`, `GARMENT_VISION_MAX_ITEMS`, `FASHION_CLIP_MODEL`, `FASHION_CLIP_ENABLED`. Operator can flip to Gemma with a single env change.
- ✅ Detection remains on Gemini 2.5 Flash for now (Gemma zero-shot bbox quality is too weak; detector is swappable independently).
- ✅ FashionCLIP embedding service (`app/services/fashion_clip.py`)
  - Lazy `torch + transformers` load (CPU) so the backend still boots if torch isn't installed.
  - `embed_image(bytes)` / `embed_text(str)` → 512-d **L2-normalised** float vectors.
  - Reports to the provider-activity ring buffer as `fashion-clip` → visible on Admin → Providers.
  - First call downloads ~600MB weights; subsequent calls are ~150-300ms on CPU.
- ✅ `/closet` integration
  - `POST /closet` now auto-computes and persists `clip_embedding` + `clip_model` on every item created with an image (soft-fail).
  - `GET /closet` strips `clip_embedding` from list responses to keep the payload lightweight.
  - **NEW** `POST /closet/search` (text or image query) → cosine-scored items with `_score` field, honours `limit` / `min_score`.
- ✅ Native camera capture on `/closet/add`
  - `Take photo` primary button (rear camera via `<input capture="environment">` on mobile; graceful file-picker fallback on desktop).
  - `Upload photos` secondary button alongside.
  - Action bar shows `Take another` + `Add more` once at least one card is present.
  - All new controls wear `data-testid` attributes for test automation.

**Architecture note on the Gemma HF path**
Gemma-family multimodal models are currently only routable via Featherless AI on the free HF Inference Providers tier, and Featherless' implementation rejects the standard `content: [text, image_url]` list payload with a "Conversation roles must alternate" error. The dispatch code is fully wired and unit-tested end-to-end for the structure of requests it will send; we simply haven't enabled it as the default because the upstream is unreliable. The moment the user's fine-tune is hosted on a stable endpoint (HF Dedicated Inference Endpoint, Modal, Replicate, their own Gemma endpoint, etc.), the swap is a one-line env change:

```
GARMENT_VISION_PROVIDER=hf
GARMENT_VISION_MODEL=<their hf repo or endpoint url>
```

**Device strategy for the eventual on-edge Eyes**
- The Eyes → Gemma 4 **E2B** (~1.3 GB Q4, ~60% of 2026 mobile install base)
- The Brain → Gemma 4 **E4B** (~2.5 GB Q4, flagship phones)
- Older devices transparently fall back to the server `/analyze` endpoint.

**Testing**
- ✅ `/app/test_reports/iteration_8.json`: backend 85%, frontend 95%, **0 critical bugs, 0 UI bugs, 0 integration issues**.
- Two "issues" flagged by the agent were false alarms: (a) `multi=true` returning 1 item for a tight single-garment photo is the intentional "already cropped" short-circuit (contract is still `items[]`); (b) embedding failure on 1×1 synthetic images is not reachable in production.
- Live manual verification: Gemini analyzer 20s + valid 17-field JSON, FashionCLIP image↔image cosine 1.000 self-match, text query "black motorcycle jacket" returns the moto-jacket item with score 0.32.

---

## 3) Next Actions (immediate)
1. **PayPlus discovery (deferred)**: when PayPlus credentials are available:
   - confirm sandbox/prod endpoints
   - confirm payout model
   - implement checkout + webhooks + DB field migration
2. **Gemma migration (future)**: when your Gemma 4 E4B fine-tune is ready:
   - set `GARMENT_VISION_PROVIDER` + `GARMENT_VISION_MODEL`
   - validate JSON contract + field completeness vs Gemini
3. Optional production hardening (nice-to-have, not blocking):
   - structured JSON logs + request IDs propagated through provider_activity
   - rate limits on stylist + eyes endpoints
   - deterministic E2E script (Playwright/Cypress):
     dev login → add closet item (batch) → auto-list (for_sale) → create transaction → verify ledger

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; UI stable; integration tests green.
- Phase 4:
  - ✅ Google Calendar OAuth functional (real events in stylist context)
  - ✅ Trend‑Scout runs daily and is visible in UI
  - ⏳ PayPlus payments wired end‑to‑end with webhook-driven transaction updates (pending user credentials)
- Phase 5:
  - ✅ Admin dashboard + provider observability
  - ✅ Accessibility + SEO baseline shipped
  - ✅ Test report iteration_5 green
- Add Item Overhaul:
  - ✅ Batch upload + scanning animation
  - ✅ The Eyes auto-fill with rich structured fields
  - ✅ One-click auto-listing when marketplace_intent != own
  - ✅ Test report iteration_6 green
- Multi-Item Outfit Extraction:
  - ✅ `/closet/analyze` returns an `items` array (multi-item) with backwards-compatible legacy mirror
  - ✅ Server-side bbox detection + cropping + parallel per-crop analysis
  - ✅ Frontend splits 1 upload into N editable cards with crop previews & labels
  - ✅ Test report iteration_7 green (backend 95%, 0 critical bugs)
