# DressApp — Development Plan (Core-first) **UPDATED (post Phase A + i18n initiative)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated & stabilised** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference (free tier) using **`mattmdjaga/segformer_b2_clothes`**.
  - **Image generate/edit**: Hugging Face **FLUX.1-schnell**.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, integration-tested.
- ✅ **Phase 4 shipped (partial)**: Google Calendar OAuth + Trend‑Scout autonomous agent.
- ✅ **Phase 5 shipped**: Admin dashboard, provider activity monitoring, accessibility + SEO hardening.
- ✅ **Add Item overhaul shipped**: batch upload + animated scanning + "The Eyes" auto-fill + rich closet schema + one‑click auto‑listing.
- ✅ **Multi-Item Outfit Extraction shipped**: one uploaded photo → N editable item cards with IoU-NMS dedupe + "already cropped" short-circuit.
- ✅ **Closet Bulk Delete shipped**: multi-select mode on `/closet` with confirmation dialog + parallel deletes.
- ✅ **Phase A (architecture pivot) shipped**: provider-dispatched Eyes (Gemini default, Gemma HF path ready), **local FashionCLIP embeddings**, semantic search, Marketplace similar-items, native camera capture.
- ⏳ **Phase 6 Model Merge & Hosting (P0)**: off-pod merge of fine-tuned Gemma 4 E2B LoRA adapter → merged model → GGUF export + hosting (blocked on external execution).
- 🆕 **Internationalization (i18n) initiative (P0)**: curated 12-language UI with full RTL mirroring for Hebrew/Arabic + per-user language persistence + AI output localization.
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
    - extended `ClosetItem` fields (materials/colors/pattern/season/etc.)

- ✅ The Eyes analyzer (Gemini 2.5 Pro multimodal, swappable)
  - `/app/backend/app/services/garment_vision.py`
  - `POST /api/v1/closet/analyze`
    - strict JSON contract
    - emits provider activity: `garment-vision`

- ✅ Extended closet create with auto-listing
  - `POST /api/v1/closet` accepts all new fields
  - auto-listing for `marketplace_intent in {for_sale,donate,swap}`

- ✅ Frontend batch upload + editing UX
  - `/app/frontend/src/pages/AddItem.jsx`

**Testing**
- ✅ Add Item overhaul test pass: `/app/test_reports/iteration_6.json`

---

### Multi-Item Outfit Extraction — One photo → N cards **(COMPLETE)**
**User stories**
1. ✅ User uploads one outfit photo containing multiple pieces.
2. ✅ The Eyes detects every item (Gemini bounding-box detector).
3. ✅ Backend crops each bbox server-side (Pillow), drops tiny / full-frame detections.
4. ✅ Each crop is re-analysed in parallel for the rich form payload.
5. ✅ Frontend replaces the single upload card with `N` editable cards.
6. ✅ Graceful fallback to single-item analysis when detection fails.

**Delivered**
- ✅ Backend orchestration in `/app/backend/app/services/garment_vision.py` + `/app/backend/app/api/v1/closet.py`
- ✅ Frontend expansion logic in `/app/frontend/src/pages/AddItem.jsx`

**Testing**
- ✅ Multi-item extraction test pass: `/app/test_reports/iteration_7.json`

---

### Phase A — Architecture pivot toward Gemma-on-edge **(COMPLETE)**
Lays the groundwork for the user's fine-tuned Gemma 4 E2B (Eyes) / E4B (Brain) edge deployment. Default Eyes provider remains Gemini until a stable hosted endpoint is available.

**Delivered**
- ✅ Provider-dispatched analyser in `garment_vision.py`
- ✅ Config surface in `app/config.py` (`GARMENT_VISION_PROVIDER`, `GARMENT_VISION_MODEL`, etc.)
- ✅ FashionCLIP embedding service (`/app/backend/app/services/fashion_clip.py`)
- ✅ Closet semantic search: `POST /api/v1/closet/search`
- ✅ Marketplace similar-items: `GET /api/v1/listings/{id}/similar`
- ✅ Native camera capture on `/closet/add`

**Testing**
- ✅ `/app/test_reports/iteration_8.json`

---

### Phase 6 — Fine-tuned Gemma 4 E2B Merge + GGUF Export + Hosting **(P0 / BLOCKED OFF-POD)**
Goal: replace Gemini for "The Eyes" with the user's fine-tuned Gemma 4 E2B.

**Status**
- ⏳ Blocked due to pod ephemeral storage limits (~30GB). Requires external machine / Colab.

**Delivered in-repo (handoff)**
- ✅ `/app/scripts/pog_phase6_merge_gguf.ipynb`
- ✅ `/app/POG_PHASE6_HANDOFF.md`

**Next steps (user-run)**
1. Run the notebook externally to:
   - download base model
   - merge LoRA adapter `pog_phase6_model`
   - export merged weights
   - convert to GGUF (llama.cpp)
2. Host the model (local server / HF endpoint / dedicated inference).
3. Update backend `.env`:
   - `GARMENT_VISION_ENDPOINT_URL=<hosted endpoint>` (or set provider/model vars as instructed)

**Validation after hosting**
- Backend verification: confirm `/api/v1/closet/analyze` routes to endpoint and returns valid JSON.

---

### Phase L — Internationalization (i18n) + RTL + AI localization **(NEW / P0)**
Adds a language selector (Settings/Profile only) with curated translations and full RTL mirroring for Hebrew & Arabic. Persists per-user in DB via `preferred_language` (already present).

#### Phase L1 — i18n Infrastructure **(IN PROGRESS)**
**Scope**
- Curated language set (Option A):
  - `en`, `he` (RTL), `ar` (RTL), `es`, `fr`, `de`, `it`, `pt`, `ru`, `zh` (Simplified), `ja`, `hi`.

**Implementation steps**
1. Frontend deps:
   - Install: `i18next`, `react-i18next` (optional: `i18next-browser-languagedetector` if needed later).
2. Create i18n bootstrap:
   - `/app/frontend/src/lib/i18n.js` with:
     - resources mapping to `locales/*.json`
     - default/fallback language `en`
     - interpolation + react options
3. Add translation resources:
   - `/app/frontend/src/locales/{en,he,ar,es,fr,de,it,pt,ru,zh,ja,hi}.json`
   - Define a stable key namespace (e.g. `nav.*`, `common.*`, `closet.*`, `addItem.*`, `admin.*`, etc.).
4. Language + direction sync:
   - Add `LanguageSync` component that:
     - reads `user.preferred_language`
     - calls `i18n.changeLanguage(lang)`
     - sets `document.documentElement.lang = lang`
     - sets `document.documentElement.dir = rtl|ltr`
     - sets a CSS hook attribute/class (e.g. `data-dir="rtl"`) for targeted styling
   - Mount it once globally (App shell) so it affects **all pages including Admin**.
5. Bootstrap in `/app/frontend/src/index.js` (import `i18n.js` before rendering).

**Definition of done**
- App loads in `en` by default; if user has `preferred_language=he|ar`, entire app renders RTL directionally.

#### Phase L2 — Language Selector in Profile/Settings **(PENDING)**
**Implementation steps**
1. Replace the current stub language select in `/app/frontend/src/pages/Profile.jsx` (currently `['en','es','fr','de','it','ja','nl']`) with the curated 12 language list.
2. Display native language names (e.g. English, עברית, العربية, Español, Français, Deutsch, Italiano, Português, Русский, 中文(简体), 日本語, हिन्दी).
3. Persist per-user:
   - On Save (or optionally immediate on change): call `api.patchMe({ preferred_language })`.
   - Update local auth user via `updateUserLocal` so the whole UI updates immediately.
4. Ensure selector is **only** in Profile/Settings (per requirement).

**Definition of done**
- Changing language updates UI without refresh and persists across devices (server-driven on login/refresh).

#### Phase L3 — UI String Extraction + Translation Coverage **(PENDING)**
**Scope**
- Translate everything user-visible including Admin dashboards.

**Implementation steps**
- Replace hard-coded strings with `t('...')` across:
  - Navigation + shell: `TopNav`, `BottomTabs`, `AppLayout`
  - Auth: `Login`, `Register`
  - Pages: `Home`, `Closet`, `AddItem`, `ItemDetail`, `Stylist`, `Marketplace`, `CreateListing`, `ListingDetail`, `Transactions`, `Admin`, `Profile`
  - Common components/toasts/empty states in `components/` and `lib/` helpers.

**Definition of done**
- No major UI labels remain hard-coded in English (except brand name / proper nouns).

#### Phase L4 — RTL Mirroring Audit (Hebrew/Arabic) **(PENDING)**
**Requirement**
- Full layout mirroring (sidebars, icon alignment, paddings/margins) — not just text direction.

**Implementation steps**
1. Tailwind audit:
   - Replace `ml-*`/`mr-*` and `pl-*`/`pr-*` where necessary.
   - Prefer logical direction utilities if available; otherwise use `[dir="rtl"]` overrides.
2. Icons and chevrons:
   - Ensure icons that imply direction mirror in RTL (e.g. arrows, chevrons).
   - For lucide icons, flip with `rtl:scale-x-[-1]` style approach (or CSS on `[dir="rtl"] .icon-directional`).
3. Components with alignment assumptions:
   - Dropdown menus, dialogs, form labels, table columns (Admin) and pagination.

**Definition of done**
- Hebrew/Arabic feel native: mirrored alignment, readable forms, correct menu anchoring.

#### Phase L5 — AI Output Localization (Stylist + The Eyes) **(PENDING)**
Ensure all AI-generated text respects `user.preferred_language`.

**Implementation steps**
1. Stylist:
   - Update `/app/backend/app/services/gemini_stylist.py` to include the user’s preferred language in the system prompt and/or response schema requirements.
   - Ensure memory summaries and final advice are in that language.
2. The Eyes:
   - Update `/app/backend/app/services/garment_vision.py` prompt to:
     - return human-readable string fields (e.g. `caption`, `repair_advice`) in the selected language
     - keep enum fields in canonical English tokens if the DB/schema expects enums (avoid breaking validations)
3. API surface:
   - Confirm `POST /api/v1/stylist/chat` and `POST /api/v1/closet/analyze` have access to user context and pass language through.

**Definition of done**
- Stylist responses and descriptive text fields from The Eyes appear in the chosen language.

#### Phase L6 — Testing **(PENDING)**
1. Backend test (language persistence):
   - Verify `PATCH /api/v1/users/me` persists `preferred_language`.
   - Verify `GET /api/v1/users/me` returns updated value.
2. Frontend manual verification:
   - Switch language in Settings → immediate UI update.
   - Reload / logout-login → language remains.
   - Hebrew/Arabic RTL mirroring verified (TopNav, BottomTabs, forms, Admin tables).
3. Screenshot tool pass for RTL pages.

---

## 3) Next Actions (immediate)
1. **Internationalization Phase L (P0)**
   - Implement L1 → L2 first (infrastructure + selector + persistence), then L3/L4 for full translation/RTL completeness.
2. **Phase 6 model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
3. **PayPlus discovery (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.
4. Optional production hardening (nice-to-have):
   - structured JSON logs + request IDs propagated through provider_activity
   - rate limits on stylist + eyes endpoints
   - deterministic E2E script (Playwright/Cypress):
     dev login → add closet item → auto-list → create transaction → verify ledger

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
  - ✅ `/closet/analyze` returns an `items` array with backwards-compatible legacy mirror
  - ✅ Server-side bbox detection + cropping + parallel per-crop analysis
  - ✅ Frontend splits 1 upload into N editable cards with crop previews & labels
  - ✅ Test report iteration_7 green
- Phase A:
  - ✅ Provider-dispatched Eyes routing + FashionCLIP embeddings + semantic search + similar items
  - ✅ Test report iteration_8 green
- **Phase L (i18n):**
  - ⏳ Curated 12-language UI available via Settings
  - ⏳ Language persists per-user across devices
  - ⏳ Hebrew/Arabic full RTL mirroring (layout + icons)
  - ⏳ Stylist + The Eyes descriptive output respects selected language
- Phase 6:
  - ⏳ Fine-tuned Gemma 4 E2B merged + exported to GGUF and hosted; backend uses it via endpoint/env switch
