# DressApp — Development Plan (Core-first) **UPDATED (post Phase T completion)**

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
- ✅ **Phase L Internationalization (i18n) initiative (P0)**: curated 12-language UI with full RTL mirroring for Hebrew/Arabic + per-user language persistence + AI output localization.
- ✅ **Phase L+ Taxonomy & Menus Translation Sweep (P0)**: no English leakage in dropdowns/menus in Hebrew mode (verified by screenshots).
- ✅ **Post-L+ follow-up**: Stylist language reliability improved (prompt preamble); and **sub_category/item_type display localization** (taxonomy mappings + hints + The Eyes directive updated).
- ✅ **Phase M System-native Speech (STT/TTS)**: Web Speech API (native) with Groq/Deepgram fallback.
- ✅ **Phase P Outfit Completion**: weighted centroids + weather awareness + UI reorder.
- ✅ **Phase Q Wardrobe Reconstructor**: HF FLUX outpainting + category-drift validation + manual Repair workflow.
- ✅ **Item Detail Edit Page**: full manual editor for closet items.
- ✅ **Phase R shipped**: **Multi-session Stylist + Fashion Scout side panel + chat image evidence**.
- ✅ **Phase S shipped**: **Device Access (Location UX) + Marketplace proximity + Region-aware Fashion Scout + share/invite + Professional CTA scaffold**.
- ✅ **Phase T shipped (NEW)**: **Extended Profile & Settings** (full schema + UI + OAuth autofill).
- 🎯 **Next after Phase T**: PayPlus payments integration — deferred until API credentials are available.

> **Operational note:** EMERGENT_LLM_KEY budget is topped up with auto‑recharge. Text/multimodal calls (Stylist + The Eyes + Fashion‑Scout) are expected to be stable, but transient upstream 503s may still occur (handled gracefully).

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
- ✅ `/app/scripts/poc_stylist_pipeline.py`

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
**User stories (Phase 2)**
1. ✅ CRUD closet items with `source=Private|Shared|Retail`.
2. ✅ Upload item photo via URL or base64 (best‑effort segmentation).
3. ✅ Authenticated stylist grounded in closet + weather + session history.
4. ✅ Public marketplace browse (filters) + seller-owned listing CRUD.
5. ✅ Transaction ledger creation with **7% platform fee after processing fee math** (payments wiring deferred).

**Phase 2 delivered (authoritative file list)**
- ✅ Auth & security
  - `/app/backend/app/services/auth.py`
  - `/app/backend/app/api/v1/auth.py`
- ✅ User profile
  - `/app/backend/app/api/v1/users.py`
- ✅ Closet
  - `/app/backend/app/api/v1/closet.py`
  - `/app/backend/app/services/hf_segmentation.py`
  - `/app/backend/app/services/hf_image_service.py`
  - `/app/backend/app/services/garment_vision.py` (The Eyes)
- ✅ Marketplace
  - `/app/backend/app/api/v1/listings.py`
  - `/app/backend/app/api/v1/transactions.py`
- ✅ Stylist agent
  - `/app/backend/app/services/stylist_memory.py`
  - `/app/backend/app/services/logic.py`
  - `/app/backend/app/api/v1/stylist.py`
  - `/app/backend/app/services/gemini_stylist.py`
- ✅ Data layer
  - `/app/backend/app/services/repos.py`
  - `/app/backend/app/db/database.py`

---

### Phase 3 — Frontend V1 (React) **(COMPLETE + Add Item upgraded)**
**User stories (Phase 3)**
1. ✅ Register/login + one-tap dev login.
2. ✅ Add and manage closet items.
3. ✅ Stylist chat: image+text, image+voice, audio playback.
4. ✅ Browse marketplace listings + fee/net breakdown.
5. ✅ Create/manage listings from closet items.
6. ✅ View ledger/transactions.

---

### Phase 4 — Context + Autonomy + Payments (PayPlus) **(PARTIALLY COMPLETE / PAYPLUS DEFERRED)**

#### Phase 4 (Part 1) — Google Calendar OAuth (P0) **(COMPLETE)**
Delivered previously; unchanged.

#### Phase 4 (Part 2) — Fashion‑Scout Background Agent (P1) **(COMPLETE)**
- ✅ Scheduled generator runs daily and persists cards.
- ✅ Extended schema to support optional media fields (image/video/source) for the Stylist side panel.

#### Phase 4 (Part 3) — PayPlus Payments (replaces Stripe) **(NEXT / DEFERRED)**
Delivered previously; unchanged.

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 6 — Fine-tuned Gemma 4 E2B Merge + GGUF Export + Hosting **(P0 / BLOCKED OFF-POD)**
Goal: replace Gemini for "The Eyes" with the user's fine-tuned Gemma 4 E2B.

Status unchanged: blocked due to pod storage limits; off-pod notebook handoff exists.

---

### Phase L — Internationalization (i18n) + RTL + AI localization **(P0 / COMPLETE)**

**Post-L hardening shipped (note)**
- ✅ Stylist reliably respects live UI language:
  - backend prefers `language` form field over DB preference
  - Gemini prompt includes explicit in-message language preamble
- ✅ `sub_category` and `item_type` localization improvements:
  - `taxonomy.sub_category.*` and `taxonomy.item_type.*` added
  - frontend shows localized hint beneath free-text fields when matched
  - The Eyes language directive updated to allow localized sub_category/item_type for new analyses

---

### Phase L+ — Taxonomy & Menus Translation Sweep **(P0 / COMPLETE)**
Delivered previously; unchanged (plus the post-L notes above).

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

### Phase O — Gemma 4 E4B Stylist Brain **(P2 / NOT STARTED)**
Delivered previously; unchanged.

---

### Phase R — Multi-session Stylist + Fashion Scout side panel **(P0 / COMPLETE)**
Delivered previously; unchanged.

---

### Phase S — Device Access + Contacts UX + Region-aware Scout + Professionals scaffold **(P0 / COMPLETE)**

#### Phase S.0 — Product constraints (web vs native) **(ACKNOWLEDGED)**
DressApp is currently a web app:
- ✅ **Location**: supported via `navigator.geolocation` on HTTPS.
- ⚠️ **Contacts**: full device address-book access is not available cross-browser on the web.
  - Best-effort (Android Chrome): Contact Picker API (`navigator.contacts.select`).
  - Universal: Web Share API (`navigator.share`) + clipboard fallback.

#### Phase S.A — Location permission + propagation **(COMPLETE)**
- ✅ `LocationProvider` + `useLocation()` hook (`/app/frontend/src/lib/location.jsx`)
  - Permission state + local caching + reverse geocode (Nominatim)
  - Persists to `users.home_location`
- ✅ In-app first-run banner (`LocationBanner`) on Home/Stylist/Market
- ✅ Profile Location settings card (refresh + forget)

#### Phase S.B — Marketplace proximity **(COMPLETE)**
- ✅ Backend: `/listings` supports `lat,lng,radius_km` via `$geoNear` and returns `distance_km`.
- ✅ Frontend: radius selector + distance chips.

#### Phase S.C — Region-aware Fashion Scout localization **(COMPLETE)**
- ✅ `trend_reports` now supports per-language cards with cached translation on-demand (Gemini Flash).
- ✅ API: `GET /trends/fashion-scout?language=…&country=…`
- ✅ Frontend: Fashion Scout panel passes user language + device/home country code.

#### Phase S.D — Contacts UX (web-first) + Share/Invite **(COMPLETE)**
- ✅ `ShareOutfitButton` on outfit recommendations (Web Share API + clipboard fallback).
- ✅ `InviteFriendsButton` on Profile (Web Share API + clipboard fallback).
- ✅ Minimal share backend:
  - `POST /share/outfit` and `GET /share/outfit/{id}`

#### Phase S.E — Professionals scaffold **(COMPLETE)**
- ✅ Disabled "Ask a professional" CTA on Stylist composer + location-aware copy.

---

### Phase T — Extended Profile & Settings **(P0 / COMPLETE)**

**Goal**: Build a complete Profile & Settings experience matching the required signup/profile layout, with selective autofill from OAuth.

#### Phase T.A — Backend schema + update API **(COMPLETE)**
- ✅ User doc extended:
  - `first_name`, `last_name`, `phone`, `date_of_birth`, `sex`, `personal_status`
  - `address` (nested)
  - `units` (weight/length)
  - `face_photo_url`, `body_photo_url`
  - `body_measurements` (nested)
  - `hair` (nested)
- ✅ `UpdateUserIn` accepts all of the above.

#### Phase T.B — OAuth-derived autofill (Google) **(COMPLETE)**
- ✅ `calendar_service.persist_tokens_for_user` now auto-fills on first connect:
  - `display_name`, `first_name`, `last_name`, `avatar_url`, `locale`
  - **Never clobbers** existing user-entered values.

#### Phase T.C — Frontend Profile UI **(COMPLETE)**
- ✅ New `ProfileDetailsCard.jsx` (7-section accordion):
  1) Identity
  2) Contact
  3) Demographics
  4) Preferences — Units
  5) Photos
  6) Body measurements
  7) Hair
- ✅ Conditional female-only rows (Bra size, Dress size) appear when `sex=female`.
- ✅ Photo slots support camera (mobile `capture=user`) + file upload.
- ✅ Photos are downscaled client-side (1024px JPEG @ q=0.82) before persisting to Mongo (data URL).
- ✅ Measurements grid labels units based on preference (cm/in, kg/lb).
- ✅ i18n: 12 locale files updated (EN/HE/AR curated, rest English fallback).
- ✅ “Auto-filled from Google — edit anytime” badge when Google has provided any identity fields.

#### Phase T.D — Verification **(COMPLETE)**
- ✅ API PATCH round-trip verified (200 + persisted fields).
- ✅ Screenshots in EN + HE confirm every section renders; female-only fields appear correctly.

**Follow-up considerations (not required for Phase T)**
- Consider blob storage (S3/R2) for photos once user growth warrants it.
- Feed `body_measurements` into stylist prompts for fit-check reasoning (future phase).

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| **P0** | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| **P1** | Phase 4 (Part 3) — PayPlus payments | PayPlus credentials | User credentials |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |
| P2 | Fit-check Stylist upgrade using `body_measurements` | Phase T data available | None |
| P3 | Phase R polish: rename sessions + mobile UX | Phase R shipped | None |
| P3 | Photo blob store migration (S3/R2) | user scale | None |

---

## 3) Next Actions (immediate)
1. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
2. **PayPlus discovery + integration (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.
3. **Fit-check prompt upgrade (P2)**
   - Add `users.body_measurements` + `users.units` to stylist context.
   - Add “fit risk” warnings (too tight/too long/etc.) and size suggestions.
4. **Shared outfit viewer (P2)**
   - Add a `/shared/:id` public page that renders the shared outfit nicely (currently API exists; UI viewer is the next step).
5. **Photo storage strategy (P3)**
   - Evaluate S3/R2 for `face_photo_url/body_photo_url` once growth increases.

---

## 4) Success Criteria
- Phase 1: ✅ shipped.
- Phase 2: ✅ shipped and tested.
- Phase 3: ✅ shipped; UI stable; integration tests green.
- Phase 4:
  - ✅ Google Calendar OAuth functional (real events in stylist context)
  - ✅ Trend‑Scout runs daily and is visible in UI
  - ✅ Fashion‑Scout feed supports optional media and powers Stylist side panel
  - ⏳ PayPlus payments wired end‑to‑end with webhook-driven transaction updates
- Phase 5:
  - ✅ Admin dashboard + provider observability
  - ✅ Accessibility + SEO baseline shipped
- Phase L/L+:
  - ✅ Curated 12-language UI available via Settings
  - ✅ Language persists per-user across devices
  - ✅ Hebrew/Arabic full RTL mirroring
  - ✅ Stylist + The Eyes descriptive output respects selected language
  - ✅ Dropdown/menu taxonomy fully localized
  - ✅ Sub-category/item-type display localization improvements shipped
- Phase M:
  - ✅ Native STT/TTS works where supported; fallback preserved
- Phase P:
  - ✅ Outfit completion works end-to-end; weather-aware rationale; weighted centroid reorder UI
- Phase Q:
  - ✅ Reconstructor repairs bad crops automatically when flagged; manual repair works; validated results persist
  - ✅ Item Detail full edit page shipped
- Phase R:
  - ✅ Multi-session conversations: sidebar list + AI titles + New Conversation clears and starts a new session
  - ✅ Chat uses only current session context; switching session swaps history
  - ✅ Fashion Scout panel shows a news-flash feed with media tiles (image/video when present)
  - ✅ Stylist chat recommendations include at least one relevant image when possible
- Phase S:
  - ✅ First-run mobile location prompt (in-app rationale + native browser permission)
  - ✅ Location persisted to profile and used for weather + Market proximity
  - ✅ Fashion Scout localized by language+country (cached per day)
  - ✅ Share outfit + invite flows via Web Share API and robust fallbacks
  - ✅ Professional CTA scaffold visible (coming soon)
- **Phase T**
  - ✅ Extended profile schema persisted and patchable via `/users/me`
  - ✅ OAuth autofill from Google userinfo populates identity fields without clobbering edits
  - ✅ Profile UI supports all required sections (Identity/Contact/Demographics/Units/Photos/Measurements/Hair)
  - ✅ Camera/upload photos stored (downscaled) and reloaded correctly
  - ✅ i18n coverage for new fields (EN/HE/AR curated)
- Phase 6 / N:
  - ⏳ Fine-tuned Gemma 4 E2B merged + hosted; `/api/v1/closet/analyze` uses it via endpoint/env switch
