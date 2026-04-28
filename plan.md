# DressApp — Development Plan (Core-first) **UPDATED (post-production stabilisation + Stylist Power-Up spec lock)**

## 1) Objectives

### ✅ Production stabilisation (dressapp.co) — **SHIPPED & VERIFIED**
- ✅ **Google OAuth redirect mismatch** fixed in production env.
- ✅ **Ad-blocker hardening**: renamed all `/ads` endpoints → `/promotions` (backend + frontend).
- ✅ **Add Item UX upgrades**:
  - Sticky “Save all” action bar.
  - Background batch upload (>5 items) with concurrent workers + progress UI.
- ✅ **Demo seeding**: `backend/scripts/seed_demo.py` added + tested.
- ✅ **Docker build hardening**:
  - Backend dependencies stabilized (legacy resolver + emergent extra index).
- ✅ **Hetzner VPS access**: passwordless SSH (ED25519) configured.
- ✅ **Closet crash + slowness fixed on production**:
  - Root cause #1: MongoDB Atlas M0 32MB sort cap → added `allow_disk_use(True)` + compound index `(user_id, created_at -1)`.
  - Root cause #2: `/api/v1/closet` payload was massive due to base64 `*_image_url` blobs.
    - Added thumbnailing + response stripping + frontend cache (stale-while-revalidate).
  - Result: Closet loads reliably and quickly, no 30s reload loop on navigation.
- ✅ **Frontend API base URL fix**: ensured `DOMAIN` is set so `REACT_APP_BACKEND_URL` bakes correctly (fixed “Unsupported protocol” axios error).
- ✅ **Stylist production 500 fixed**:
  - Root cause: `repos.find_one()` lacked `sort` kwarg → crashed `get_or_create_active_session`.
  - Added `sort=` support to `repos.find_one`.
- ✅ **Direct Gemini (production)**:
  - `GEMINI_API_KEY` supported; chat calls route directly to Google via litellm (no Emergent proxy).
  - Model split: **Pro for Stylist**, **Flash for The Eyes/Trend-Scout**.
  - Nano Banana (`gemini-2.5-flash-image`) integrated for reconstruction when direct key present.

### 🎯 Current product direction — **Stylist Power-Up (Outfit Composer)**
Make the Stylist uniquely valuable by enabling:
1. **Multi-image upload** in Stylist chat AND a dedicated **Compose Outfit** page.
2. **Outfit construction** from uploaded items with:
   - near-duplicate removal (e.g., 3 shirts → pick best 1)
   - brief matching + cohesion scoring
   - reject list with rationale
3. **Marketplace gap fill (LIVE)**: if outfit missing shoes/outerwear/etc., suggest better matches from **Marketplace listings**.
4. **Professional referral (heuristic-triggered)**: suggest a relevant pro from the `/professionals` directory when repair/tailoring/special-occasion/fit risk signals appear.
5. **Model-agnostic architecture**: keep LLM calls behind a thin shim so swapping to fine-tuned **Gemma 4** models later is single-file.

> **Operational note (updated):** Production no longer depends on Emergent universal key for core LLM. `GEMINI_API_KEY` is the primary production path; `EMERGENT_LLM_KEY` remains as dev fallback.

---

## 2) Implementation Steps

### Phase 1 — Core POC (isolation) + required docs **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 2 — V1 App Development (backend-first MVP) **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 3 — Frontend V1 (React) **(COMPLETE + Add Item upgraded)**
Delivered previously; unchanged.

---

### Phase 4 — Context + Autonomy + Payments (PayPal) **(SHIPPED 🎉)**
Delivered previously; unchanged.

---

### Phase 5 — Admin + Hardening + Comprehensive E2E **(COMPLETE)**
Delivered previously; unchanged.

---

### Phase 6 / N — Fine-tuned Gemma 4 E2B Merge + GGUF Export + Hosting **(P0 / BLOCKED OFF-POD)**
Goal: replace Gemini for “The Eyes” with the user’s fine-tuned Gemma model.

Status unchanged: blocked due to off-pod merge/hosting.

---

### Phase R — **Stylist Power-Up: Outfit Composer** **(P0 / NEW)**
This phase extends the already-shipped multi-session Stylist by adding a *composer pipeline* and a rich outfit canvas.

#### R.0 — Finalise UX + schema contract **(P0)**
**Decisions locked (user):** **1c + 2c + 3d + 4a + 5b**
- Multi-image upload in **Stylist chat** + dedicated **Compose Outfit** page.
- Output: chat bubble summary + **tap-to-expand canvas**.
- Marketplace search live; Places/retail feeds deferred but architecture-ready.
- Pro referral: **heuristic-triggered**.
- MVP includes marketplace integration.

**Deliverables**
- Define payload schema `OutfitCanvas` (versioned) persisted inside `StylistMessage`.
- Define ranking contract for:
  - uploaded candidates
  - closet alternatives
  - marketplace alternatives

#### R.1 — Backend pipeline **(P0)**
**New endpoint**
- `POST /api/v1/stylist/compose-outfit`
  - multipart: `images[]`, `text` (brief), `language`, optional `constraints` (budget, dress_code, season, must_include, avoid)
  - returns: `{ canvas, message, rejected, marketplace_suggestions, professional_suggestion }`

**Services**
- `app/services/outfit_composer.py`
  - Per-image analysis (reuse The Eyes/closet-analyze pipeline)
  - Candidate normalization → category inference, dominant colors, pattern, formality
  - **Dedup**:
    - exact dup by hash
    - near-dup by CLIP similarity / tag overlap
    - keep best by quality score
  - Brief scoring: match vs (occasion, weather, dress_code, palette, modesty)
  - Outfit assembly: fill slots (top/bottom/dress/outerwear/shoes/accessory)
  - Gap detection + fallback to closet items
- `app/services/marketplace_search.py`
  - Query `listings` filtered by: category, region proximity (existing Phase S), price range
  - Rank by: tag overlap, color harmony, embedding similarity (optional)
- `app/services/professional_matcher.py`
  - Heuristic triggers: “tailor”, “repair”, “hem”, “dry-clean”, “wedding”, “funeral”, “interview”, “fit risk”, “cultural/traditional constraint”
  - Select top pros from `/professionals` using region/profession + optional language match

**Schemas** (add to `app/models/schemas.py`)
- `CandidateGarment`
- `OutfitCanvas`
- `MarketplaceSuggestion`
- `ProfessionalSuggestion`

**Persistence**
- Store composer outputs as a `StylistMessage` subtype payload:
  - `kind='outfit_canvas'`
  - `outfit_canvas={...}`
  - ensures the canvas survives chat history + sharing.

**Reliability**
- Never 500 due to LLM/provider failure:
  - return an “empty canvas” with clear error + retry suggestion
  - record provider failures in provider_activity

#### R.2 — Frontend integration **(P0)**
**Stylist chat upgrades**
- `Stylist.jsx`
  - Attach button + multi-image preview chips
  - “Send” becomes “Compose Outfit” when attachments present
  - Upload progress + cancel

**Compose Outfit page**
- New route: `/stylist/compose`
  - Multi-image dropzone + brief
  - Advanced filters (budget, dress code, must/avoid)

**Outfit canvas UI**
- New reusable component: `OutfitCanvas.jsx`
  - Head-to-toe layout (slots)
  - “Rejected” panel with rationale (duplicates, mismatched formality, color clash)
  - Marketplace strip (gap-fill suggestions)
  - Pro card (only when triggered)
- Chat bubble: compact summary + “View Outfit” CTA (opens modal/route).

#### R.3 — Polish + Testing **(P0)**
**Test scenarios**
- 3 shirts + 1 pant upload:
  - ensure 2 shirts rejected as duplicates/unmatched
  - outfit uses 1 selected shirt + pant
  - missing shoes triggers marketplace suggestions
- Language support:
  - Hebrew + English briefs
  - ensure canvas labels localized
- Performance:
  - cap uploads per request (e.g., 8)
  - bounded concurrency for vision analysis

---

### Phase Q+ — Wardrobe Reconstructor migration note **(SHIPPED)**
- Production now prefers **Nano Banana** image edit/generation when `GEMINI_API_KEY` is present.
- HF FLUX remains dev fallback.

---

## 3) Next Actions (immediate)

### P0 (now)
1. **Phase R — Stylist Power-Up (Outfit Composer)**
   - Implement backend endpoint + composer services
   - Implement frontend attachments + canvas + compose page
   - Wire marketplace live suggestions
   - Heuristic-trigger pro referral

### P1
2. Calendar sync deep-dive (OAuth completes but events not syncing reliably in all deployments).

### P2 (blocked)
3. Phase 6/N: merge and host fine-tuned Gemma 4 E2B (The Eyes).
4. Phase O: Gemma 4 E4B Stylist brain swap.

---

## 4) Success Criteria

### Production health
- ✅ Closet loads quickly (
  - no Mongo sort memory failure,
  - no multi-MB list payload,
  - navigation back to closet is instant due to cache
)
- ✅ Stylist endpoint returns 200 consistently (no `repos.find_one(sort=...)` crash)
- ✅ Frontend bundle has valid `REACT_APP_BACKEND_URL` and makes API calls without protocol errors

### Phase R — Stylist Power-Up (Outfit Composer)
- Multi-image upload supported in chat and dedicated compose page.
- Dedupe works (reject duplicates; pick best candidate).
- Outfit constructed with visible slots and clear rationale.
- Marketplace gap-fill suggestions appear when outfit incomplete.
- Professional referral appears only when heuristic triggers.
- Model-agnostic: swapping to Gemma 4 models does not require changing frontend payload contracts.
