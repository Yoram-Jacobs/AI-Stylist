# DressApp — Development Plan (Core-first) **UPDATED (post Phase R completion)**

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
- 🎯 **Next after Phase R**: PayPlus payments integration — deferred until API credentials are available.

> **Operational note:** EMERGENT_LLM_KEY budget is topped up with auto‑recharge. Text/multimodal calls (Stylist + The Eyes + Trend‑Scout/Fashion‑Scout) are expected to be stable, but transient upstream 503s may still occur (handled gracefully).

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

#### Phase 4 (Part 2) — Trend‑Scout Background Agent (P1) **(COMPLETE; now upgraded into Fashion‑Scout)**
- ✅ Scheduled generator runs daily and persists cards.
- ✅ Extended schema to support optional media fields for the Stylist side panel (Phase R).

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

**Problem statement (delivered)**
- ✅ Stylist page needed ChatGPT-style multi-session threads:
  - Left rail showing past conversations
  - Only the active conversation is loaded/rendered
  - “New Conversation” clears chat and starts a fresh session, while keeping context within the same session.
- ✅ Stylist page side panel needed **Fashion Scout** results as a news-flash feed with images/videos.
- ✅ Stylist recommendations in chat needed at least one illustrative image to “prove/show” the recommendation.

#### Phase R.A — Backend: multi-session conversations **(COMPLETE)**
**Shipped**
1. `StylistSession` schema:
   - ✅ Added `title`, `snippet`, `archived` fields.
2. Memory store rewrite:
   - ✅ `/app/backend/app/services/stylist_memory.py` now supports multiple sessions per user.
   - ✅ Added helpers: `list_sessions`, `create_session`, `get_session`, `update_session`, `delete_session`, `full_history`.
   - ✅ Kept compatibility alias: `get_or_create_session = get_or_create_active_session`.
3. Title generation:
   - ✅ `/app/backend/app/services/session_titles.py` generates localized 3–5 word titles via Gemini 2.5 Flash.
   - ✅ Fallback: first ~5 words.
4. API changes:
   - ✅ `POST /api/v1/stylist` accepts optional `session_id` and returns `{session_id, session, advice}`.
   - ✅ `GET /api/v1/stylist/history?session_id=...` returns per-session full history.
   - ✅ New routes:
     - `GET /api/v1/stylist/sessions`
     - `POST /api/v1/stylist/sessions`
     - `DELETE /api/v1/stylist/sessions/{id}`
5. DB indexes:
   - ✅ Dropped legacy unique index `stylist_sessions.user_id_1`.
   - ✅ Added compound index: `(user_id, last_active_at desc)`.

#### Phase R.B — Backend: Fashion Scout enrichment API **(COMPLETE)**
**Shipped**
1. Buckets expanded (7):
   - ✅ runway (`ss26-runway`), street, sustainability, influencers, second_hand, recycling, news_flash.
2. Trend report schema expanded:
   - ✅ `source_name`, `source_url`, `image_url`, `video_url`.
   - ✅ URL sanitisation to avoid obviously unsafe/fake links.
3. Endpoint:
   - ✅ `GET /api/v1/trends/fashion-scout?limit=12` returns newest-first flat feed.

#### Phase R.C — Frontend: Stylist page 3-panel redesign **(COMPLETE)**
**Shipped**
- ✅ Desktop layout:
  - Left: `ConversationSidebar` (sessions + New Conversation)
  - Center: `ChatPanel` (messages for active session only)
  - Right: `FashionScoutPanel` (news-flash feed)
- ✅ Mobile/tablet:
  - Sidebar and Scout panel available via slide-in drawers (`Sheet`).
- ✅ Components:
  - `/app/frontend/src/components/stylist/ConversationSidebar.jsx`
  - `/app/frontend/src/components/stylist/FashionScoutPanel.jsx`
  - `/app/frontend/src/components/stylist/OutfitRecommendationCard.jsx` (embeds closet images)
- ✅ API helpers:
  - `/app/frontend/src/lib/api.js`:
    - `stylistSessions`, `stylistCreateSession`, `stylistDeleteSession`, `stylistHistory(sessionId, limit)`
    - `fashionScoutFeed(limit)`
- ✅ i18n:
  - 12 locale files updated with new `stylist.*` keys (EN/HE/AR curated; others English fallback).

#### Phase R.D — Verification / QA **(COMPLETE)**
- ✅ Screenshot-verified in Hebrew + English:
  1. 3-panel layout renders on desktop breakpoints.
  2. Left sidebar lists sessions ordered by last active; AI-generated 3–5 word titles.
  3. Clicking sessions swaps chat content (only one visible).
  4. New Conversation clears chat and starts fresh session.
  5. Fashion Scout panel renders a feed with media tiles + source links; gradient fallback when missing.
  6. Assistant outfit cards embed closet-item images when `closet_item_id` is present.

**Known optional polish (not shipped)**
- Inline rename UI for sessions (server already stores `title`, but no frontend editor).
- Multi-language Fashion Scout generation per-user locale (currently single daily generation).
- Mobile drawer UX refinements (gesture polish, persistent open state).

---

### Roadmap Priority & Sequencing
| Priority | Phase | Depends On | Blocker |
| --- | --- | --- | --- |
| P0 | Phase 6 / N — Finish Gemma 4 E2B merge (The Eyes) | — | User off-pod notebook execution |
| P1 | Phase 4 (Part 3) — PayPlus payments | PayPlus credentials | User credentials |
| P2 | Phase O — Gemma 4 E4B Stylist Brain | Phase N pattern, user fine-tune | User fine-tune + hosting |
| P3 | Trend‑Scout/Fashion‑Scout multi-language generation | i18n infra | Product decision |
| P3 | Phase R polish: rename sessions + mobile UX | Phase R shipped | None |

---

## 3) Next Actions (immediate)
1. **Phase 6 / N model merge (P0 / blocked)**
   - User runs `/app/scripts/pog_phase6_merge_gguf.ipynb` off-pod.
   - After hosting, set `GARMENT_VISION_ENDPOINT_URL` and run backend verification.
2. **PayPlus discovery + integration (P1 / deferred)**
   - When credentials arrive: confirm sandbox/prod endpoints, payout model, implement checkout + webhooks.
3. **Optional Phase R polish (P3)**
   - Session rename UI.
   - Fashion Scout locale strategy (generate per-language or translate at read-time).
   - Mobile drawer UX polish.

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
- Phase 6 / N:
  - ⏳ Fine-tuned Gemma 4 E2B merged + hosted; `/api/v1/closet/analyze` uses it via endpoint/env switch
