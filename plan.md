# DressApp — Development Plan (Core-first) **UPDATED (post Phase A + Phase L completion)**

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
- ⏳ **Phase 6 Model Merge & Hosting (P0)**: off-pod merge of fine-tuned Gemma 4 E2B LoRA adapter → merged model → GGUF export + hosting (blocked on external execution).
- ✅ **Phase L Internationalization (i18n) initiative (P0)**: curated 12-language UI with full RTL mirroring for Hebrew/Arabic + per-user language persistence + AI output localization + backend tests green.
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

### Phase L — Internationalization (i18n) + RTL + AI localization **(P0 / COMPLETE)**
Adds a language selector (Settings/Profile only) with curated translations and full RTL mirroring for Hebrew & Arabic. Persists per-user in DB via `preferred_language` (already present). Localizes AI outputs while keeping enum tokens stable.

#### Phase L1 — i18n Infrastructure **(COMPLETE)**
**Delivered**
- ✅ Frontend deps installed: `i18next`, `react-i18next`
- ✅ i18n bootstrap:
  - `/app/frontend/src/lib/i18n.js`
  - Curated 12-language set: `en`, `he` (RTL), `ar` (RTL), `es`, `fr`, `de`, `it`, `pt`, `ru`, `zh` (Simplified), `ja`, `hi`
- ✅ Translation resources:
  - `/app/frontend/src/locales/{en,he,ar,es,fr,de,it,pt,ru,zh,ja,hi}.json`
- ✅ Global language + direction sync:
  - `/app/frontend/src/components/LanguageSync.jsx`
  - Sets `html[lang]` and `html[dir=rtl|ltr]`
- ✅ Bootstrapped in `/app/frontend/src/index.js` and mounted in `/app/frontend/src/components/AppLayout.jsx`

#### Phase L2 — Language Selector in Profile/Settings **(COMPLETE)**
**Delivered**
- ✅ Prominent language selector card at the top of `/me`:
  - Native names + English names
  - Immediate apply via `i18n.changeLanguage()`
  - Persists per-user via `api.patchMe({ preferred_language })`
  - Also mirrors to `localStorage` (`dressapp.lang`) for fast initial paint

#### Phase L3 — UI String Extraction + Translation Coverage **(COMPLETE, with fallback behavior)**
**Delivered**
- ✅ Core shell + high-traffic pages translated:
  - `TopNav`, `BottomTabs`, `AppLayout`
  - `Login`, `Register`, `Home`, `Profile`, `Closet`
- ✅ Remaining pages (e.g. Admin, Marketplace, ListingDetail, AddItem, Stylist, Transactions, etc.) may still have English strings in places, but:
  - i18next fallback is `en`, so UI remains coherent
  - AI output localization still respects chosen language

#### Phase L4 — RTL Mirroring Audit (Hebrew/Arabic) **(COMPLETE)**
**Delivered**
- ✅ `LanguageSync` sets document direction globally
- ✅ Directional layout fixes:
  - Converted `ml-/mr-` → `ms-/me-` where needed
  - Directional arrows use `rtl:rotate-180`
- ✅ Screenshot-verified: full RTL mirroring on Hebrew (nav alignment, avatar/menu placement, content alignment)

#### Phase L5 — AI Output Localization (Stylist + The Eyes) **(COMPLETE)**
**Delivered**
- ✅ Stylist localization:
  - `/app/backend/app/services/gemini_stylist.py` injects a language directive using `user.preferred_language`
- ✅ The Eyes localization:
  - `/app/backend/app/services/garment_vision.py`
    - `analyze(..., language=...)` and `analyze_outfit(..., language=...)`
    - directive localizes free-text fields while **keeping enum-ish fields in English** to avoid schema validation issues
  - `/app/backend/app/api/v1/closet.py` threads `user.preferred_language` into `/closet/analyze`

#### Phase L6 — Testing **(COMPLETE)**
- ✅ Backend: `/app/test_reports/iteration_9.json` (testing_agent_v3) — **17/17 pass (100%)**
  - persistence across all 12 language codes
  - Stylist Hebrew + Spanish localized
  - The Eyes Hebrew localized; enums preserved
  - no endpoint regressions
- ✅ Frontend: screenshot_tool verified language switching and RTL mirroring

---

## Roadmap Additions — Audit-Approved (Web-First, NOT a React Native Rewrite)

> **Context:** The user reviewed a large proposal to rewrite DressApp in React Native + Dify + Ollama + ComfyUI. After audit, the user explicitly chose to **keep the current FastAPI + React web stack** and extract only the **4 features below** as incremental roadmap phases. All items below are additive; none require a rewrite.

### Phase M — System-Native Speech (STT + TTS) **(P1 / COMPLETE)**
Replaced the paid/external speech stack (Groq Whisper-v3 for STT, Deepgram Aura-2 for TTS) with the user's device-native speech capabilities via the browser Web Speech API, **with graceful server-side fallback intact for unsupported browsers (e.g., Firefox desktop)**. Zero new API keys, zero per-minute cost on supported devices, dramatically lower latency.

**User stories**
1. ✅ When the user taps the mic in the Stylist, the app uses `SpeechRecognition` (webkit prefix on iOS/Safari, native on Chrome/Edge/Android) to transcribe speech locally.
2. ✅ When the Stylist returns a reply, the app uses `SpeechSynthesis` with a voice matching `user.preferred_language` (respects all 12 UI locales where the OS has a voice).
3. ✅ Graceful fallback to the existing Groq/Deepgram pipeline on browsers that lack Web Speech API support (e.g., Firefox desktop).

**Delivered**
- Frontend
  - ✅ `/app/frontend/src/lib/speech.js` — wraps `window.SpeechRecognition` / `window.webkitSpeechRecognition` + `window.speechSynthesis` with:
    - `isSTTSupported()` / `isTTSSupported()` feature detection
    - `createRecognition({ lang, onInterim, onFinal, onError, onEnd })` — BCP-47 locale mapping for all 12 app locales (`en`→`en-US`, `he`→`he-IL`, `ar`→`ar-SA`, `zh`→`zh-CN`, etc.)
    - `speak(text, lang, { onStart, onEnd, onError })` + `cancelSpeak()` with async voice loading (`ensureVoicesLoaded`) and a pickVoice() helper that matches exact → language-family → bare-language fallback
  - ✅ `/app/frontend/src/pages/Stylist.jsx`:
    - Mic button now prefers native STT; falls back to MediaRecorder + `/api/v1/stylist` voice_audio upload when `isSTTSupported()===false`
    - Live interim transcript bubble shown while dictating (`data-testid="stylist-interim-transcript"`)
    - Native-speech capability badge in the header (`data-testid="stylist-native-speech-badge"`)
    - On assistant reply: when no server audio present, renders a **"Play reply"** / **"Stop speaking"** button that drives local `speechSynthesis` with the user's `preferred_language` (Volume2 / VolumeX icons)
  - ✅ i18n keys added to `en.json` + `he.json`: `listening`, `tapToStop`, `speechUnsupported`, `nativeSpeech`, `stopSpeaking`, `playReply` (other locales fallback to English per Phase L strategy)
- Backend
  - ✅ `/app/backend/app/api/v1/stylist.py` — added `skip_tts: bool = Form(default=False)` parameter, plumbed into `get_styling_advice(..., synthesize_tts=not skip_tts)`. No new endpoints.
  - ✅ Existing Groq Whisper + Deepgram Aura-2 paths fully preserved for fallback.

**Verification**
- ✅ Backend smoke tests (live against the preview URL):
  - `skip_tts=true` → `tts_audio_base64: null`, `spoken_reply` + `reasoning_summary` populated, HTTP 200
  - default (skip_tts omitted) → `tts_audio_base64` present (~133KB base64 MP3)
  - Hebrew localization + `skip_tts=true` → Hebrew reply + no audio (Phase L × Phase M interop)
- ✅ Frontend screenshot verification on Chromium:
  - "NATIVE SPEECH" badge renders in header
  - After a fresh send, the assistant reply shows the "Play reply" button (no waveform player)
  - `PLAY_BUTTONS: 1, STOP_BUTTONS: 0` exactly as expected before play
- ✅ Lint + esbuild bundle clean (no new errors)

**Success criteria**
- ✅ Stylist conversations complete end-to-end with zero Deepgram audio returned on supported browsers (skip_tts=true path).
- ✅ Voice output uses the correct locale voice when available; falls back to English voice otherwise.
- ✅ Firefox desktop still works via the existing server-side fallback (backend paths untouched).

---

### Phase N — Finish Gemma 4 E2B LoRA Merge (The Eyes) **(P0 / IN PROGRESS — see Phase 6)**
Goal: replace Gemini for `garment-vision` ("The Eyes") with the user's fine-tuned Gemma 4 E2B model.

**Status**
- Already tracked as **Phase 6** above. This roadmap item is a pointer, not a duplicate phase.
- Blocker: pod ephemeral storage limits. Off-pod notebook handed off (`/app/scripts/pog_phase6_merge_gguf.ipynb`).
- Backend is already provider-dispatched via `GARMENT_VISION_PROVIDER` / `GARMENT_VISION_MODEL` / `GARMENT_VISION_ENDPOINT_URL`.

**Remaining work (user-run)**
1. User executes the handoff notebook externally (merge LoRA → export → convert to GGUF).
2. User hosts the merged model (local server / HF dedicated endpoint / llama.cpp server).
3. User sets `GARMENT_VISION_ENDPOINT_URL` in `/app/backend/.env` and restarts the backend.
4. Verification: call `/api/v1/closet/analyze` and confirm traffic routes to the hosted endpoint (Admin → Providers tab shows `garment-vision` using the new provider).

**Success criteria**
- `/api/v1/closet/analyze` returns a valid rich-schema JSON payload with the hosted Gemma 4 E2B endpoint in the provider activity log.
- Gemini path remains intact as a safety fallback (configurable via env).

---

### Phase O — Gemma 4 E4B Stylist Brain **(P2 / NOT STARTED, depends on user fine-tuning)**
Goal: swap the Stylist LLM from Gemini 2.5 Pro/Flash to the user's fine-tuned Gemma 4 E4B once the text-only fine-tune is complete and hosted.

**User stories**
1. Logged-in users receive stylist replies generated by the user's Gemma 4 E4B model instead of Gemini.
2. The switch is behind an env flag so Gemini remains available as a fallback.
3. Multilingual output (Phase L5) continues to work — the system prompt's language directive must be preserved when swapping models.

**Scope of changes**
- Backend
  - `/app/backend/app/services/gemini_stylist.py` — add a provider-dispatch layer analogous to `garment_vision.py`:
    - `STYLIST_PROVIDER` ∈ `{gemini, gemma_e4b_endpoint}`
    - `STYLIST_MODEL`
    - `STYLIST_ENDPOINT_URL`
  - Preserve the current strict JSON contract + the `preferred_language` directive.
  - Keep provider activity logging under a new key (`gemma-stylist`) so Admin → Providers surfaces latency/error rate parity.
- No frontend changes expected.

**Blockers / prerequisites**
- User must finish the Gemma 4 E4B text fine-tune and host it (HF Inference Endpoint, llama.cpp server, or vLLM).
- Must expose an OpenAI-compatible or plain JSON chat endpoint with tool/function-calling parity sufficient for the existing Stylist JSON schema.

**Success criteria**
- `STYLIST_PROVIDER=gemma_e4b_endpoint` yields stylist responses that validate against the existing stylist JSON schema.
- Language directive honored for all 12 UI locales.
- Seamless fallback to Gemini when `STYLIST_PROVIDER=gemini` or the endpoint errors twice in a row.

---

### Phase P — Outfit Completion Task (Closet) **(P1 / NOT STARTED)**
Goal: add a first-class "complete this outfit" action in the Closet. Given 1–N user-selected items, the Stylist suggests closet items (and optionally marketplace listings) that complete the outfit, grounded in weather, calendar, and user taste.

**User stories**
1. In `/closet`, user multi-selects 1–N items (leveraging existing multi-select mode) and taps **"Complete the Outfit"**.
2. Backend builds an anchor set from those items + their FashionCLIP embeddings + rich metadata (colors/materials/season/formality).
3. Stylist returns a ranked set of **completion suggestions**:
   - **From closet:** existing items whose FashionCLIP similarity + rule-based compatibility (color harmony, season, formality) best complete the anchor.
   - **From marketplace (optional toggle):** top listings that plug gaps the closet can't fill (e.g., "no neutral outerwear for this occasion").
4. Output rendered as an Outfit Completion card with the anchor items + suggested items + a short rationale (localized via `preferred_language`).

**Scope of changes**
- Backend
  - New endpoint: `POST /api/v1/closet/complete-outfit`
    - body: `{ item_ids: [uuid], include_marketplace?: bool, occasion?: str }`
    - uses `/app/backend/app/services/fashion_clip.py` for embedding-space retrieval against the user's closet and, optionally, active listings.
    - uses `/app/backend/app/services/gemini_stylist.py` (or Gemma E4B once Phase O ships) to produce the rationale + final ranked list, grounded in weather + calendar (same context hydration as chat).
    - returns: `{ anchors: [Item], closet_suggestions: [Item], market_suggestions: [Listing], rationale: str }`.
  - Reuses existing provider activity logging.
- Frontend
  - `/app/frontend/src/pages/Closet.jsx` — add **"Complete the Outfit"** action to the existing multi-select toolbar.
  - New `/app/frontend/src/components/OutfitCompletionSheet.jsx` — renders anchors + suggestions + rationale in a bottom sheet / dialog.
  - i18n keys added to `en.json` / `he.json` / `ar.json`, fallback for the rest.

**Success criteria**
- User can select 2 items → receive a valid completion set with rationale in < 6s median.
- Suggestions respect season + formality + weather.
- Localized rationale (verified at least for `en`, `he`, `es`).
- No regression in existing closet flows; covered by a new test report iteration.

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| P0 | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| P1 | ✅ Phase M — System-native STT/TTS | — | **SHIPPED** |
| P1 | Phase P — Outfit Completion | FashionCLIP (shipped) | None (ready to start) |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |

### Explicitly Out of Scope (from the audited proposal)
- ❌ React Native / Expo rewrite of the frontend — **rejected**, keeps web app.
- ❌ Replacing FastAPI orchestration with Dify — **rejected**, keeps FastAPI.
- ❌ Running Ollama / ComfyUI inside the pod — **rejected**, pod storage + GPU constraints make this a step backward vs. the current HF + Gemini + user-hosted endpoint design.
- ❌ Removing the admin dashboard / provider activity tracker — **rejected**, it is the observability layer that unblocks Phases N and O.

---

## 3) Next Actions (immediate)
1. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
2. **Phase M — System-native STT/TTS (P1) — ✅ SHIPPED**
   - Web Speech API wired into Stylist with graceful Groq/Deepgram fallback. See Phase M section above.
3. **Phase P — Outfit Completion (P1 / ready to start)**
   - Add `POST /api/v1/closet/complete-outfit` + UI action in `Closet.jsx` multi-select toolbar.
4. **Phase O — Gemma 4 E4B Stylist (P2 / deferred)**
   - Depends on the user completing + hosting the text fine-tune. Implementation mirrors Phase N's provider-dispatch pattern.
5. **PayPlus discovery (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.
6. Optional production hardening (nice-to-have):
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
  - ✅ Curated 12-language UI available via Settings
  - ✅ Language persists per-user across devices
  - ✅ Hebrew/Arabic full RTL mirroring (layout + icons)
  - ✅ Stylist + The Eyes descriptive output respects selected language
  - ✅ Backend test report iteration_9 green
- Phase 6:
  - ⏳ Fine-tuned Gemma 4 E2B merged + exported to GGUF and hosted; backend uses it via endpoint/env switch
- **Roadmap Additions (Audit-Approved):**
  - ✅ Phase M — System-native STT/TTS live with graceful fallback (P1)
  - ⏳ Phase N — Gemma 4 E2B merge completed + routed (P0, same as Phase 6)
  - ⏳ Phase O — Gemma 4 E4B stylist provider-dispatched with fallback to Gemini (P2)
  - ⏳ Phase P — Outfit Completion endpoint + Closet UI action shipped (P1)
