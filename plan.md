# DressApp — Development Plan (Core-first) **UPDATED (post Phase L+ completion)**

## 1) Objectives
- ✅ **Phase 1 shipped**: Architecture + MongoDB schema + provider POC script.
- ✅ **Phase 2 shipped**: Fully functional backend (auth, users, closet, listings, transactions w/ fee math, stylist pipeline).
- ✅ **Vision stack migrated & stabilised** (fal.ai removed entirely):
  - **Segmentation (cutout)**: Hugging Face Inference using **`mattmdjaga/segformer_b2_clothes`**.
  - **Image generate/edit**: Hugging Face **FLUX.1-schnell**.
- ✅ **Phase 3 shipped**: React frontend compiles, screenshot‑verified, integration-tested.
- ✅ **Phase 4 shipped (partial)**: Google Calendar OAuth + Trend‑Scout autonomous agent.
- ✅ **Phase 5 shipped**: Admin dashboard, provider activity monitoring, accessibility + SEO hardening.
- ✅ **Add Item overhaul shipped**: batch upload + animated scanning + "The Eyes" auto-fill + rich closet schema + one‑click auto‑listing.
- ✅ **Multi-Item Outfit Extraction shipped**: one uploaded photo → N editable item cards with IoU-NMS dedupe + "already cropped" short-circuit.
- ✅ **Closet Bulk Delete shipped**: multi-select mode on `/closet` with confirmation dialog + parallel deletes.
- ✅ **Phase A shipped**: provider-dispatched Eyes (Gemini default, Gemma HF path ready), **local FashionCLIP embeddings**, semantic search, Marketplace similar-items, native camera capture.
- ⏳ **Phase 6 Model Merge & Hosting (P0)**: off-pod merge of fine-tuned Gemma 4 E2B LoRA adapter → merged model → GGUF export + hosting (**blocked on external execution**).
- ✅ **Phase L Internationalization (i18n) initiative (P0)**: curated 12-language UI with full RTL mirroring for Hebrew/Arabic + per-user language persistence + AI output localization + backend tests green.
- ✅ **Phase L+ Taxonomy & Menus Translation Sweep (P0)**: **no English leakage in dropdowns/menus** in Hebrew mode (verified by screenshots).
- ✅ **Phase M System-native Speech (STT/TTS)**: Web Speech API (native) with Groq/Deepgram fallback.
- ✅ **Phase P Outfit Completion**: weighted centroids + weather awareness + UI reorder.
- ✅ **Phase Q Wardrobe Reconstructor**: HF FLUX outpainting + category-drift validation + manual Repair workflow.
- ✅ **Item Detail Edit Page**: full manual editor for closet items.
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
- ✅ Frontend Home feed integration
  - `/app/frontend/src/pages/Home.jsx` reads `/api/v1/trends/latest`

#### Phase 4 (Part 3) — PayPlus Payments (replaces Stripe) **(NEXT / DEFERRED)**
**User stories**
1. Seller onboarding / payout routing using PayPlus (depends on PayPlus capabilities).
2. Buyer checkout creates a PayPlus payment session.
3. Webhooks update transaction lifecycle: `pending → paid/failed/refunded`.
4. Ledger consistency: store `gross`, `processing_fee`, `platform_fee (7% after fee)`, `seller_net`.

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 6 — Fine-tuned Gemma 4 E2B Merge + GGUF Export + Hosting **(P0 / BLOCKED OFF-POD)**
Goal: replace Gemini for "The Eyes" with the user's fine-tuned Gemma 4 E2B.

**Status**
- ⏳ Blocked due to pod ephemeral storage limits (~30GB). Requires external machine / Colab.

**Delivered in-repo (handoff)**
- ✅ `/app/scripts/pog_phase6_merge_gguf.ipynb`
- ✅ `/app/POG_PHASE6_HANDOFF.md`

---

### Phase L — Internationalization (i18n) + RTL + AI localization **(P0 / COMPLETE)**
Adds language selector, per-user persistence, full RTL mirroring for Hebrew/Arabic, and AI output localization.

**Status**
- ✅ Core i18n infra shipped and verified.

---

### Phase L+ — Taxonomy & Menus Translation Sweep **(P0 / COMPLETE)**
**Problem statement (resolved)**
User screenshot-audited 7 pages in Hebrew mode and found lingering English literals in native menus and dropdowns.

**What shipped**
1. ✅ New top-level `taxonomy` namespace in all 12 locale files.
   - Curated translations for `en/he/ar`.
   - English injected into other locales as a fallback; `fallbackLng: 'en'` still guarantees coverage.
2. ✅ New helper `/app/frontend/src/lib/taxonomy.js`:
   - `labelForCategory`, `labelForSource`, `labelForGender`, `labelForSeason`, `labelForDressCode`, `labelForPattern`, `labelForState`, `labelForCondition`, `labelForQuality`, `labelForFormality`, `labelForIntent`, `labelForRole`.
3. ✅ Refactors complete:
   - `SourceTagBadge.jsx`: localized Private/Shared/Retail.
   - `CalendarConnect.jsx`: fully localized card UI + toasts.
   - `Closet.jsx`: category/source filter labels, item card category labels, localized “No image”.
   - `AddItem.jsx`: TaxonomyGrid + QualityRow + SeasonPicker + WeightedList + TagsEditor + NameCaption + IntentSelector; scanning overlay/retry/saved/remove labels localized.
   - `ItemDetail.jsx`: `NullableSelect` + `PillMultiSelect` now accept `format`; taxonomy dropdowns and overlay category badge localized.
   - `Marketplace.jsx`: source/category filter dropdowns localized.

**QA / Verification**
- ✅ Build / bundle check passed.
- ✅ Live Hebrew-mode screenshots verified that:
  - Closet shows translated Source badges and translated category labels.
  - Add Item is fully Hebrew (labels, buttons, dropzone copy).
  - Item Detail edit form dropdown options + season pills are Hebrew.
  - Marketplace filters are Hebrew; “Shared” badge is translated.
  - Profile CalendarConnect card is fully Hebrew.

**Known residuals (documented; not a bug)**
- Free-text fields (e.g., `sub_category="Pants"`, `item_type="Shorts"`, `color="blue"`) remain in English if stored that way; these are user/AI strings, not enums.
- Trend‑Scout cards are still English (cron produces one set). Multi-language Trend‑Scout is a separate phase.

---

### Phase M — System-Native Speech (STT + TTS) **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase P — Outfit Completion Task (Closet) **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase Q — High-Fidelity Wardrobe Reconstructor **(P1 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase O — Gemma 4 E4B Stylist Brain **(P2 / NOT STARTED, depends on user fine-tuning)**
Delivered previously; unchanged.

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| P0 | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| P1 | Phase 4 (Part 3) — PayPlus payments | PayPlus credentials | User credentials |
| P1 | ✅ Phase M — System-native STT/TTS | — | Shipped |
| P1 | ✅ Phase P — Outfit Completion | FashionCLIP (shipped) | Shipped |
| P1 | ✅ Phase Q — Wardrobe Reconstructor | HF FLUX, The Eyes | Shipped |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |
| P3 | Trend‑Scout multi-language generation (new) | i18n infra | Product decision |

---

## 3) Next Actions (immediate)
1. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
2. **PayPlus discovery (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.
3. Optional production hardening (nice-to-have)
   - structured JSON logs + request IDs propagated through provider_activity
   - rate limits on stylist + eyes endpoints
   - deterministic E2E script (Playwright/Cypress)
4. (Optional) **Trend‑Scout localization follow-up (P3)**
   - Choose strategy: per-user read-time translation vs. multi-language generation at cron time.

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
- Phase L:
  - ✅ Curated 12-language UI available via Settings
  - ✅ Language persists per-user across devices
  - ✅ Hebrew/Arabic full RTL mirroring (layout + icons)
  - ✅ Stylist + The Eyes descriptive output respects selected language
- **Phase L+**:
  - ✅ In Hebrew mode, **no English leakage** in: dropdown options, source badges, CalendarConnect card, AddItem microcopy, Closet/Market filters, item card category labels.
  - ✅ Frontend build passes; screenshots confirm RTL layout remains correct.
- Phase M:
  - ✅ Native STT/TTS works where supported; fallback preserved
- Phase P:
  - ✅ Outfit completion works end-to-end; weather-aware rationale; weighted centroid reorder UI
- Phase Q:
  - ✅ Reconstructor repairs bad crops automatically when flagged; manual repair works; validated results persist
  - ✅ Item Detail full edit page shipped
- Phase 6 / N:
  - ⏳ Fine-tuned Gemma 4 E2B merged + hosted; `/api/v1/closet/analyze` uses it via endpoint/env switch
