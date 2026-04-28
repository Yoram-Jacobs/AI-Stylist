# DressApp — Development Plan (Core-first) **UPDATED (post-production stabilisation + Stylist Power-Up + Google Sign-in)**

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
- ✅ **Stylist Phase R + Phase S implementation complete (deployment pending)**:
  - Phase R: multi-image upload + outfit compose pipeline + rich `OutfitCanvas`.
  - Phase S: stylist can “search wider” (Marketplace/Fashion Scout) using user profile preferences.

### 🎯 Current product direction — **Stylist Power-Up (Outfit Composer) + Widened Search**
Make the Stylist uniquely valuable by enabling:
1. **Multi-image upload** in Stylist chat AND a dedicated **Compose Outfit** page.
2. **Outfit construction** from uploaded items with:
   - near-duplicate removal (e.g., 3 shirts → pick best 1)
   - brief matching + cohesion scoring
   - reject list with rationale
3. **Marketplace gap fill (LIVE)**: if outfit missing shoes/outerwear/etc., suggest better matches from **Marketplace listings**.
4. **Professional referral (heuristic-triggered)**: suggest a relevant pro from the `/professionals` directory when repair/tailoring/special-occasion/fit risk signals appear.
5. **Widen horizons (LIVE)**: stylist can optionally search beyond closet using Marketplace/Fashion Scout and user preferences (gender/age/body/region/style profile).
6. **Model-agnostic architecture**: keep LLM calls behind a thin shim so swapping to fine-tuned **Gemma 4** models later is single-file.

### 🔐 New must-have direction — **Phase T-Auth: Google Sign-in / Google Login**
Add **Sign in with Google** / **Log in with Google** (OAuth) to:
- verify the suspected Calendar silent-fail cause (dev/mock email vs real identity)
- simplify onboarding and reduce password friction
- unify identity between OAuth and Calendar connect

**Decisions locked (user):**
- **1c Hybrid:** Lean Google sign-in by default (`openid email profile`), with **“Also connect my calendar”** checkbox on Login.
- **2a Auto-link by email:** Google login merges into existing password account if emails match.
- **3a UI placement:** Google button on **Login + Register** pages.
- **4a Keep dev-bypass** for backwards compatibility.
- **Admin access:** `ADMIN_EMAILS` env-var allow-list (comma-separated) checked on every login/register; CLI script `grant_admin.py` as fallback.

> **Operational note:** Production no longer depends on Emergent universal key for core LLM. `GEMINI_API_KEY` is the primary production path; `EMERGENT_LLM_KEY` remains as dev fallback.

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
This phase extends the already-shipped multi-session Stylist by adding a *composer pipeline* and a rich outfit canvas.

#### R.0 — Finalise UX + schema contract **(DONE)**
- Multi-image upload in **Stylist chat** + dedicated **Compose Outfit** page.
- Output: chat bubble summary + **tap-to-expand canvas**.
- Marketplace search live; Places/retail feeds deferred but architecture-ready.
- Pro referral: **heuristic-triggered**.

#### R.1 — Backend pipeline **(DONE)**
- `POST /api/v1/stylist/compose-outfit` (multipart)
- Services:
  - `app/services/outfit_composer.py`
  - `app/services/marketplace_search.py`
  - `app/services/professional_matcher.py`
- Persistence:
  - store composer outputs inside stylist session messages.
- Reliability:
  - avoid 500s on provider failures (return empty canvas + retry hints).

#### R.2 — Frontend integration **(DONE)**
- `Stylist.jsx` upgraded:
  - multi-image attachments + previews
  - compose flow
- `OutfitCanvas.jsx` added

#### R.3 — Polish + Testing **(DONE: local smoke)**
- Backend smoke tests passed
- Frontend compiles successfully
- **Pending:** user deploy + real browser verification on VPS

---

### Phase S — **Stylist Widen Search + User Preferences** **(P0 / SHIPPED IN CODE — DEPLOYMENT PENDING)**
#### S.1 — Backend (DONE)
- New services:
  - `app/services/user_preferences.py` (extract and normalize user profile preferences)
  - `app/services/stylist_widen.py` (optional external suggestion layer)
- Updated schema:
  - `StylistAdvice` supports marketplace/scout suggestions
- Prompting:
  - injects preferences (gender/age/body/region/style profile)
  - `widen_search` flag controls whether out-of-closet suggestions are produced

#### S.2 — Frontend (DONE)
- `Stylist.jsx`:
  - “Search wider” toggle
  - renders marketplace/scout suggestions

#### S.3 — Known limitations (explicit)
- Marketplace/Fashion Scout may return 0 results when DB is unseeded

---

### Phase T-Auth — **Google Sign-in / Log in with Google** **(P0 / SHIPPED IN CODE — DEPLOYMENT PENDING)**
Implement an unauthenticated Google OAuth flow to create/login users, optionally connect Calendar in the same step.

#### T.0 — Data model + config (P0)
**Config**
- Add `ADMIN_EMAILS` env var in backend:
  - comma-separated, normalized to lowercase
  - used to auto-assign `admin` role for matching emails

**User schema alignment**
- Ensure the user doc stores Google identity in a stable place.
  - Existing model has `google_oauth` (tokens container)
  - Existing calendar connect flow currently persists to `google_calendar_tokens` (needs consolidation to avoid confusion)

> Deliverable: single source of truth for Google tokens/identity fields (either migrate to `google_oauth` or keep `google_calendar_tokens` but standardize usage). Plan is to unify during implementation.

#### T.1 — Backend OAuth flow (P0)
**Refactor calendar OAuth helper for reuse**
- Update `calendar_service.py`:
  - allow building authorization URLs with **custom scopes**
  - support **custom callback path** (calendar connect vs auth login)

**State JWT hardening**
- Extend state payload:
  - `purpose`: distinguishes
    - `google-oauth-link` (existing connect-calendar)
    - `google-oauth-login` (new sign-in)
  - include `redirect_to` (frontend path)
  - include `with_calendar` boolean

**New endpoints (in `app/api/v1/google_auth.py`)**
- `GET /api/v1/auth/google/login/start`
  - unauthenticated
  - query:
    - `with_calendar=true|false` (from checkbox)
    - `next=/path` (optional)
  - returns `{ authorization_url }`

- `GET /api/v1/auth/google/login/callback`
  - exchanges `code` → tokens
  - fetches userinfo (email)
  - **find-or-create user**:
    - if email exists: link Google identity to that user (2a)
    - else create new user with:
      - email, display_name, avatar_url, locale where available
      - `password_hash=None`
  - if `with_calendar=true`:
    - persist refresh token + calendar scope metadata
  - applies admin role via `ADMIN_EMAILS`
  - redirects to frontend `/auth/callback#token=...&next=...` (hash fragment)

**Role enforcement / admin utilities**
- `app/services/auth.py`:
  - add `apply_admin_role(user, email)` helper
  - called on register/login/google-login; idempotent

- Add CLI fallback:
  - `backend/scripts/grant_admin.py you@email.com`
  - sets `roles` to include `admin` for a given user

#### T.2 — Frontend integration (P0)
**API glue**
- `frontend/src/lib/api.js`
  - add `getGoogleLoginUrl({ withCalendar, next })`

**Login UI**
- `pages/Login.jsx`
  - add “Continue with Google” button
  - add “Also connect my calendar” checkbox
  - on click:
    - request start URL, redirect browser to Google

**Register UI**
- `pages/Register.jsx`
  - add “Continue with Google” button (no calendar checkbox by default)

**OAuth callback landing page**
- New `pages/AuthCallback.jsx`
  - reads hash fragment `#token=...&next=...`
  - persists token + user (if included)
  - redirects to `next` or `/home`

**Routing**
- Update `App.jsx` routes:
  - add `/auth/callback` route

**i18n**
- Update `locales/en.json` and `locales/he.json`:
  - button labels
  - checkbox label
  - error states

#### T.3 — Testing + verification (P0)
**Backend**
- Smoke-test start URL:
  - `GET /api/v1/auth/google/login/start?with_calendar=false`
- Callback test in real browser:
  - verify:
    - new user creation
    - existing user auto-link
    - token returned and session established
    - `ADMIN_EMAILS` grants admin only to allow-listed emails

**Frontend**
- Manual browser test:
  - Login with Google (with_calendar false)
  - Login with Google (with_calendar true)
  - Register with Google
  - Existing email+password account → Google login links correctly

**Calendar suspicion validation**
- After Google login, call:
  - `/api/v1/calendar/status`
  - `/api/v1/calendar/upcoming`
- Confirm events sync for the same real Google identity.

---

### Phase Q+ — Wardrobe Reconstructor migration note **(SHIPPED)**
- Production now prefers **Nano Banana** image edit/generation when `GEMINI_API_KEY` is present.
- HF FLUX remains dev fallback.

---

## 3) Next Actions (immediate)

### P0 (now)
1. **Phase T-Auth — Google Sign-in / Log in with Google**
   - Backend endpoints + state JWT + admin allow-list
   - Frontend buttons + callback route
   - Consolidate Google token fields (`google_oauth` vs `google_calendar_tokens`) to avoid silent-fail confusion
   - End-to-end test on VPS with real Google account

2. **Deploy Phase R + Phase S to VPS**
   - Push to GitHub
   - On VPS: pull + rebuild (`docker compose up -d --build`)
   - Verify:
     - Stylist multi-image compose works
     - “Search wider” toggle returns responses (even if empty marketplace)

### P1
3. **Calendar sync deep-dive (silent fail)**
   - After Phase T-Auth ships, debug with a real Google identity
   - Validate token persistence, scopes, refresh behavior, and Calendar API calls

### P2 (blocked)
4. Phase 6/N: merge and host fine-tuned Gemma 4 E2B (The Eyes).
5. Phase O: Gemma 4 E4B Stylist brain swap.

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

### Phase R + S — Stylist Power-Up + Widen Search
- Multi-image upload supported in chat and dedicated compose page.
- Dedupe works (reject duplicates; pick best candidate).
- Outfit constructed with visible slots and clear rationale.
- Marketplace gap-fill suggestions appear when outfit incomplete.
- “Search wider” toggle uses user preferences and can suggest out-of-closet items.

### Phase T-Auth — Google Sign-in
- Users can:
  - create an account via Google
  - log in via Google
  - optionally connect Calendar during login (checkbox)
  - seamlessly link Google identity to existing password account by email
- Admin access:
  - only emails in `ADMIN_EMAILS` receive `admin` role
  - non-admin users remain `roles: ['user']`
  - `grant_admin.py` can promote a user as fallback
- Calendar validation:
  - calendar events successfully sync for real Google identities
  - if sync fails, errors are surfaced and diagnosable (logs + status endpoint)
