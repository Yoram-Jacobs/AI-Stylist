# DressApp — Development Plan (Core-first) **UPDATED (post-production stabilisation + Stylist Power-Up + Google Sign-in + UX Polish + Dual-Deploy + Pre-deploy Audit)**

## 1) Objectives

### ✅ Production stabilisation (dressapp.co) — **SHIPPED & VERIFIED**
- ✅ **Google OAuth redirect mismatch** fixed in production env.
- ✅ **Ad-blocker hardening**: renamed all `/ads` endpoints → `/promotions` (backend + frontend).
- ✅ **Add Item UX upgrades**:
  - Sticky “Save all” action bar.
  - Background batch upload (>5 items) with progress UI.
- ✅ **Demo seeding**: `backend/scripts/seed_demo.py` added + tested.
- ✅ **Docker build hardening**:
  - Backend dependencies stabilized.
- ✅ **Hetzner VPS access**: passwordless SSH (ED25519) configured.
- ✅ **Closet crash + slowness fixed on production**:
  - Root cause #1: MongoDB Atlas M0 32MB sort cap → added `allow_disk_use(True)` + compound index `(user_id, created_at -1)`.
  - Root cause #2: `/api/v1/closet` payload massive due to base64 `*_image_url` blobs.
    - Added thumbnailing + response stripping + frontend cache (stale-while-revalidate).
  - Result: closet loads reliably + fast.
- ✅ **Frontend API base URL fix**: ensured `DOMAIN` is set so `REACT_APP_BACKEND_URL` bakes correctly.
- ✅ **Stylist production 500 fixed**:
  - Root cause: `repos.find_one()` lacked `sort` kwarg → crashed `get_or_create_active_session`.
  - Added `sort=` support.
- ✅ **Direct Gemini (production)**:
  - `GEMINI_API_KEY` supported; chat calls route directly to Google (no Emergent proxy).
  - Model split: **Pro for Stylist**, **Flash for The Eyes/Trend-Scout**.
  - Nano Banana (`gemini-2.5-flash-image`) integrated for reconstruction when direct key present.
- ✅ **Stylist Phase R + Phase S implementation complete (deployment pending)**:
  - Phase R: multi-image upload + outfit compose pipeline + rich `OutfitCanvas`.
  - Phase S: stylist can “search wider” (Marketplace/Fashion Scout) using user profile preferences.

### ✅ UX Polish (post-listing/auth fixes) — **SHIPPED IN CODE — DEPLOYMENT PENDING**
Small high-impact UX fixes to eliminate “did it save?” ambiguity and missing visual feedback.
- ✅ **Create Listing**
  - Show thumbnail preview for linked closet item (uses `thumbnail_data_url`).
  - Post-publish redirect: **/market**.
- ✅ **Item Detail (Edit item)**
  - Post-save redirect: **/closet**.
  - “Clean background” action uses real **shadcn Progress** bar:
    - animated, asymptotic ramp to **92%**, snap to **100%** on completion.
- ✅ **Settings / Profile**
  - Post-save redirect: **/home**.

### 🎯 Current product direction — **Stylist Power-Up (Outfit Composer) + Widened Search**
Make the Stylist uniquely valuable by enabling:
1. Multi-image upload in Stylist chat and a dedicated Compose Outfit page.
2. Outfit construction with dedupe, cohesion scoring, rationale.
3. Marketplace gap-fill suggestions.
4. Pro referral (heuristics).
5. Search wider beyond closet using preferences + marketplace/scout.
6. Model-agnostic LLM shim for future Gemma swap.

### 🔐 Must-have direction — **Phase T-Auth: Google Sign-in / Google Login**
Add Sign in with Google / Log in with Google to:
- validate Calendar silent-fail cause using real Google identity
- reduce password friction
- unify identity between OAuth and Calendar connect

**Decisions locked (user):**
- **1c Hybrid:** Google sign-in default + “Also connect my calendar” checkbox.
- **2a Auto-link by email:** merge into existing password account if emails match.
- **3a UI placement:** Google button on Login + Register.
- **4a Keep dev-bypass** for backwards compatibility.
- **Admin access:** `ADMIN_EMAILS` allow-list; `grant_admin.py` as fallback.

> **Operational note:** Production no longer depends on Emergent universal key for core LLM. `GEMINI_API_KEY` is primary; `EMERGENT_LLM_KEY` is dev fallback.

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

### Phase R — **Stylist Power-Up: Outfit Composer** **(P0 / SHIPPED IN CODE — DEPLOYMENT PENDING)**
This phase extends the multi-session Stylist by adding a composer pipeline and rich outfit canvas.

#### R.0 — Finalise UX + schema contract **(DONE)**
- Multi-image upload in Stylist chat + Compose Outfit page.
- Output: chat bubble summary + tap-to-expand canvas.
- Marketplace search live; retail feeds deferred but architecture-ready.
- Pro referral heuristic-triggered.

#### R.1 — Backend pipeline **(DONE)**
- `POST /api/v1/stylist/compose-outfit` (multipart)
- Services:
  - `app/services/outfit_composer.py`
  - `app/services/marketplace_search.py`
  - `app/services/professional_matcher.py`
- Persistence: composer outputs stored in stylist session messages.
- Reliability: provider failures return empty canvas + retry hints (no 500).

#### R.2 — Frontend integration **(DONE)**
- `Stylist.jsx` upgraded: multi-image attachments + previews + compose flow.
- `OutfitCanvas.jsx` added.

#### R.3 — Polish + Testing **(DONE: local smoke)**
- Backend smoke tests passed.
- Frontend compiles.
- Pending: user deploy + real browser verification on VPS.

---

### Phase S — **Stylist Widen Search + User Preferences** **(P0 / SHIPPED IN CODE — DEPLOYMENT PENDING)**
#### S.1 — Backend **(DONE)**
- Services:
  - `app/services/user_preferences.py`
  - `app/services/stylist_widen.py`
- Schema: `StylistAdvice` supports marketplace/scout suggestions.
- Prompting injects preferences (gender/age/body/region/style profile).

#### S.2 — Frontend **(DONE)**
- “Search wider” toggle + rendering of marketplace/scout suggestions.

#### S.3 — Known limitations
- Marketplace/Fashion Scout may return 0 results when DB is unseeded.

---

### Phase T-Auth — **Google Sign-in / Log in with Google** **(P0 / SHIPPED IN CODE — DEPLOYMENT PENDING)**
Implement unauthenticated Google OAuth to create/login users, optionally connect Calendar.

(Implementation details unchanged from prior plan; still needs VPS deploy + real account verification.)

---

### Phase Z — **Pre-deployment audit (current)** **(SHIPPED IN CODE — DEPLOYMENT PENDING)**
A consolidation phase capturing the work shipped in this session, plus the repo-wide lint + documentation audit required before deployment.

#### Z.1 — UX polish pack **(DONE)**
- Create Listing: linked-item thumbnail preview + redirect to `/market`.
- Item Detail: redirect to `/closet` after save.
- Profile: redirect to `/home` after save.
- Clean background progress: shimmer replaced with `Progress` component + simulated progress ramp.

#### Z.2 — Batch upload pipeline reliability **(DONE)**
- Frontend: `handleBatchBackground` now sequential (no parallelism on small VPS), retry-with-backoff; surfaces `analyzeFailed` counts in final toast.
- Backend: added process-wide `_ANALYZE_LOCK = asyncio.Semaphore(1)`; applied to `analyze_outfit`, `analyze`, and new `reanalyze`.

#### Z.3 — Edit page regression fix: restore weighted taxonomy **(DONE)**
- Extracted `WeightedList` from `AddItem.jsx` → `frontend/src/components/WeightedList.jsx`.
- `ItemDetail.jsx` now exposes and edits:
  - `colors[]` (weighted, percentage)
  - `fabric_materials[]` (weighted, percentage)
- `diffPatch` upgraded with deep-compare for object arrays (fixes perpetual dirty state).

#### Z.4 — Re-analyse + replace-photo UX **(DONE)**
- Backend: `POST /api/v1/closet/{id}/reanalyze`
  - re-runs The Eyes on stored image (segmented → reconstructed → original)
  - overwrites analyser-owned fields only; preserves user-managed metadata
  - mirrors dominant weighted `colors/fabric_materials` into legacy `color/material`
- Frontend: Item Detail now has **Analyze** button + progress.
- Replace photo now uses `autoSegment:false` so user explicitly triggers Clean Background / Analyze.

#### Z.5 — Over-cropping regression fix (graphic-print shredding) **(DONE)**
- `clothing_parser._split_instances` now treats single-garment classes as non-splittable:
  - `Upper-clothes`, `Dress`, `Skirt`, `Pants`
- Prevents shredding into multiple instances when prints break SegFormer mask continuity.
- Marker: `single_instance_classes_v1=true`.

#### Z.6 — Size auto-derivation from user preferences **(DONE)**
- New `frontend/src/lib/size_preferences.js` deriving size from `user.body_measurements`:
  - Top/Outerwear → `shirt_size`
  - Bottom → `pants_size`
  - Footwear → `shoe_size`
  - Full-body/Dress → `dress_size` (fallback `shirt_size`)
  - Underwear/bra → `bra_size` (as applicable)
- Wired into AddItem `hydrate()` and ItemDetail `toFormState()` symmetrically (prevents `isDirty` flapping).

#### Z.7 — Dual-deploy support for Emergent host **(DONE)**
Goal: make `https://ai-stylist-api.emergent.host` function with equivalent user-facing behaviour despite low pod resources.

- Split dependencies:
  - `backend/requirements.txt` — lightweight deps (installed by Emergent host)
  - `backend/requirements-ml.txt` — heavy ML (torch/transformers/rembg/scipy/onnxruntime/etc.)
- Updated `deploy/Dockerfile.backend` to install both files for Hetzner.
- Removed unused `cuda-*` packages from default deps.
- Added runtime auto-detection in `app/config.py`:
  - probes `torch`, `transformers`, `rembg` via `find_spec`
  - defaults `USE_LOCAL_CLOTHING_PARSER` and `AUTO_MATTE_CROPS` based on installed modules
- Updated default CORS origins to include `https://ai-stylist-api.emergent.host`.
- Added live markers on `GET /api/v1/closet/analyze/version`:
  - `torch_installed`, `rembg_installed`, `use_local_clothing_parser`, `auto_matte_crops`

#### Z.8 — Pre-deploy audit + docs refresh **(DONE)**
- Backend lint: ruff clean.
- Frontend lint: ESLint clean.
- esbuild: bundle compiles.
- Locales: all 12 JSON-valid.
- `server.py` cold-imports cleanly; routes registered.
- Docs updated:
  - README: dual-deploy story + requirements split.
  - ARCHITECTURE.md: updated deployment modes, `_ANALYZE_LOCK`, `/reanalyze`, dual-deploy.

---

### Phase Q+ — Wardrobe Reconstructor migration note **(SHIPPED)**
- Production prefers Nano Banana when `GEMINI_API_KEY` present.
- HF FLUX remains dev fallback.

---

## 3) Next Actions (immediate)

### P0 (now)
1. **Deploy Phase Z bundle to Hetzner**
   - On VPS: `git pull` + rebuild: `docker compose up -d --build`
   - Verify in real browser:
     - Create Listing shows linked-item thumbnail preview
     - Create Listing publish redirects to `/market`
     - Item Detail save redirects to `/closet`
     - Clean background shows Progress bar + completes
     - Profile save redirects to `/home`
     - Replace Photo stores raw photo (no auto-segmentation)
     - Analyze button re-fills colors/materials with percentages
     - Batch upload >5 items: each item is analysed (no “first item ok, rest blank”) and final toast reports any `analyzeFailed` items
     - Graphic-print tees no longer shred into multiple cropped fragments
     - Size defaults to user preference when analyzer cannot infer it

2. **Redeploy Emergent host (`ai-stylist-api.emergent.host`)**
   - Confirm deploy no longer 520.
   - Probe `GET /api/v1/closet/analyze/version`:
     - Expect `torch_installed:false`, `rembg_installed:false`, `use_local_clothing_parser:false`, `auto_matte_crops:false`.
   - Validate core flows still work (with fallback ML path): Add Item, Analyze, Stylist, Marketplace.

3. **Deploy Phase R + Phase S to VPS**
   - Pull + rebuild.
   - Verify stylist multi-image compose and “Search wider”.

4. **Phase T-Auth verification on VPS (real Google account)**
   - Verify login, account-linking by email, optional calendar connect.
   - Validate calendar endpoints and error surfacing.

### P1
5. **Calendar sync deep-dive (silent fail)**
   - After Phase T-Auth ships, debug with real identity.
   - Validate token persistence, scopes, refresh behaviour, and Calendar API calls.

### P2 (blocked)
6. Phase 6/N: merge and host fine-tuned Gemma 4 E2B (The Eyes).
7. Phase O: Gemma 4 E4B Stylist brain swap.

---

## 4) Success Criteria

### Production health
- ✅ Closet loads quickly (no Mongo sort memory failure, no multi-MB payload, cache works).
- ✅ Stylist endpoint stable (no `repos.find_one(sort=...)` crash).
- ✅ Frontend bundle has correct API base URL.

### Phase Z (pre-deploy audit) bundle
- ✅ UX polish behaviour present (previews + redirects + progress).
- ✅ Batch upload does not skip analysis after first item; `_ANALYZE_LOCK` prevents concurrent OOM.
- ✅ Edit page shows weighted `colors[]` and `fabric_materials[]` with percentages.
- ✅ Replace photo is raw; user triggers background removal + analyze explicitly.
- ✅ `POST /closet/{id}/reanalyze` works, preserves user fields.
- ✅ Graphic-print tees do not shred.
- ✅ Size defaults from user body measurements when missing.
- ✅ Emergent host deploy works without torch/rembg (fallback path), and `analyze/version` markers reflect mode.

### Phase R + S — Stylist Power-Up + Widen Search
- Multi-image upload in chat and compose page.
- Outfit constructed with visible slots and rationale.
- Marketplace gap-fill suggestions appear when outfit incomplete.
- “Search wider” uses user preferences and can suggest out-of-closet items.

### Phase T-Auth — Google Sign-in
- Users can:
  - create an account via Google
  - log in via Google
  - optionally connect Calendar during login
  - auto-link to existing password account by email
- Admin access:
  - only `ADMIN_EMAILS` get `admin` role
  - `grant_admin.py` fallback works
- Calendar validation:
  - events sync for real Google identities
  - failures are surfaced and diagnosable (logs + status endpoint)
