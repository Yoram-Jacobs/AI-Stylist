# DressApp — Development Plan (Core-first) **UPDATED (post Phase S kickoff)**

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
- 🎯 **Current milestone (NEW)**: **Phase S — Device Access (Location + Contacts UX) + Region-aware Fashion Scout + Professionals scaffold**.
- 🎯 **Next after Phase S**: PayPlus payments integration — deferred until API credentials are available.

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

### Phase S — Device Access + Contacts UX + Region-aware Scout + Professionals scaffold **(P0 / NOT STARTED)**

#### Phase S.0 — Product constraints (web vs native)
DressApp is currently a web app:
- ✅ **Location**: supported via `navigator.geolocation` on HTTPS.
- ⚠️ **Contacts**: full device address-book access is *not* available on the web across browsers.
  - Best-effort on web: **Contact Picker API** (`navigator.contacts.select`) is mostly Chromium-on-Android.
  - Universal alternative: **Web Share API** (`navigator.share`) + copy link + manual entry.
- ✅ This Phase S will implement a web-first permission [design that can later map 1:1 to native permissions when wrapped (Capacitor/Expo).

#### Phase S.A — Location permission + propagation (P0)
**Goal**: On mobile, request location on first run; use it for Marketplace proximity, weather context, nearby stores (future), Professionals (future), and Fashion Scout regionalization.

**Scope**
1. Frontend: `LocationProvider` + `useLocation()` hook
   - Tracks permission state: `prompt | granted | denied | unavailable`.
   - Stores `{ coords, accuracy_m, city, country_code, lastUpdatedAt }`.
   - First-run prompt logic (mobile-friendly): show a single in-app explanation screen that triggers `navigator.geolocation.getCurrentPosition()`.
   - Persist the "asked" state in `localStorage` per-device.

2. Frontend: first-run permission UX
   - Trigger on first visit after installation (practically: first app run on that browser profile).
   - Display rationale: Marketplace nearby, weather-aware stylist, local stores, Professional matching (later), Fashion Scout localization.
   - Provide "Not now" and "Try again".

3. Backend/user persistence
   - Persist location to `users.home_location` via existing `PATCH /users/me`.
   - Add/confirm `home_location` shape: `{ lat, lng, city, country_code, updated_at }`.

4. Reverse geocoding
   - Use Nominatim (no key) with aggressive caching (rounded lat/lng) to avoid rate limits.

5. Marketplace proximity
   - Extend marketplace/listings read endpoints to accept `lat`, `lng`, `radius_km`.
   - Sort by proximity and return `distance_km`.
   - Frontend: radius selector + "Near you" chip on each card.

#### Phase S.B — Region-aware Fashion Scout localization (P0)
**Goal**: localize Fashion Scout cards by language + country.

**Scope**
1. Data model updates
   - Extend `trend_reports` docs with `language` (default: `en`) and optional `country_code`.

2. API
   - Update `GET /trends/fashion-scout` to accept `language` and `country` query params.
   - If localized cards exist for today: return them.
   - Else: translate/regionalize from canonical English cards using Gemini Flash and upsert per `(bucket, date, language, country)`.
   - Fail-soft: return English when translation fails.

3. Frontend plumbing
   - Pass `i18n.language` and `country_code` (from location or profile) when fetching Fashion Scout feed.

#### Phase S.C — Ask a Professional scaffold (P0)
- Add a disabled "Ask a Professional" button (localized) on Stylist composer with a "Coming soon" tooltip.
- Copy adapts when location is available (e.g., "Connect with a local stylist"), but no logic implemented yet.

#### Phase S.D — Contacts UX (P1 pragmatic, web-first)
**Goal**: allow users to share outfits for approval and invite contacts, while acknowledging web limitations.

**Scope**
1. Share outfit
   - Add `ShareOutfitButton` on outfit recommendation cards.
   - Use `navigator.share` when available; fallback to copy link.

2. Invite friends
   - Add `InviteFriendsButton` on Profile.
   - Uses `navigator.share` [with a pre-filled message + download link.
   - Fallback: copy link + QR code.

3. Optional scaffolding: Contact picker
   - Feature-detect `navigator.contacts.select`.
   - Provide "Pick from contacts" option on supported Android Chrome; otherwise hide/disable.

4. Optional scaffolding: share-link backend
   - `POST /share/outfit` mints a UUID and stores a read-only snapshot.
   - `GET /share/outfit/{id}` renders a public view page.
   - **Approval/chat flows** are explicitly out of scope for Phase S (future phase).

**Out of scope (future)**
- Capacitor/Expo native wrapper with real native permissions for contacts.
- Real-time chat between users.
- Professional directory + booking + payments.
- Full contact/address book sync.

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| **P0** | **Phase S — Device Access + Contacts UX + Region-aware Scout + Professional scaffold** | Web APIs + UI | None |
| P0 | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| P1 | Phase 4 (Part 3) — PayPlus payments | PayPlus credentials | User credentials |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |
| P3 | Phase R polish: rename sessions + mobile UX | Phase R shipped | None |

---

## 3) Next Actions (immediate)
1. **Phase S (P0): Location-first-run UX + persistence + Marketplace proximity**
   - Implement `LocationProvider` + first-run prompt
   - Persist `home_location` to user profile
   - Add radius filters + distance chip for Market
2. **Phase S (P0): Fashion Scout localization by language+country**
   - Add language/country-aware caching and endpoint params
   - Wire frontend to pass locale + region
3. **Phase S (P1): Contacts UX via Share + Invite**
   - Web Share API + copy/QR fallback
   - Optional contact picker scaffolding
4. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
5. **PayPlus discovery + integration (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.

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
- **Phase S (NEW)**
  - ⏳ First-run mobile location prompt (in-app rationale + native browser permission)
  - ⏳ Location persisted to profile and used for weather + Market proximity
  - ⏳ Fashion Scout localized by language+country (cached per day)
  - ⏳ Share outfit + invite flows via Web Share API and robust fallbacks
  - ⏳ Professional CTA scaffold visible (coming soon)
- Phase 6 / N:
  - ⏳ Fine-tuned Gemma 4 E2B merged + hosted; `/api/v1/closet/analyze` uses it via endpoint/env switch
