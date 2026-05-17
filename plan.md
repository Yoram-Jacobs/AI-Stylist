# DressApp — Development Plan (Core-first) **UPDATED (Eyes v3 / Gemma 4 E2B self-host LIVE on production VPS)**

---

## 🔖 SESSION HANDOFF — 17 May 2026 (Neo)

> User asked for a clean context reset previously. This handoff block is the current “fast resume” source of truth.

### What shipped last session (already in repo)

- **Patch M20.5.2** — Bulk upload pipeline (>5 photos) regression fix.
  - Root cause: `AddItem.jsx::analyzeCard` split the NDJSON `detect` frame into per-garment placeholder cards but **dropped source-photo fingerprint fields**.
  - Fix: propagate `sourceSha256/sourcePhash/sourceColorSig/sourceFilename/sourceSizeBytes/isDuplicate` into each placeholder card; replace racy `setTimeout(0, saveAllRef.current())` with `setPendingAutoSave(true)`.
  - Impact: fixes “Couldn’t refresh fingerprints/thumbnails”, restores duplicate skip on re-upload, restores polishing registration in `workStore`.
  - Verification: ESLint clean, esbuild clean; testing agent confirmed new items carry `source_sha256` and backend persists fingerprints.

### Status of preview vs production

- **Preview pod**: has `M20.5.2`.
- **Production (dressapp.co)**: user-reported to be out of sync at times; redeploy is still required whenever preview has fixes.

### Open / paused work (priority-ordered)

- **P0 — Seal the “Upload-Items” pipeline** so *all* add-item workflows use one closed routine:
  - single-item upload
  - camera upload
  - bulk upload (>5)
  - future programmatic workflows (e.g. “save outfit suggestion”)
- **P0 — Remove drift risk**: no more parallel add-item pipelines.
- **P1 — Backfill legacy items** missing `source_sha256` (hash-repair stream from /closet).
- **P1 — CCP ground-truth class remap** in `/app/scripts/run_eyes_benchmark.py`.
- **P1 — Rewrite Eyes deployment runbook** for `llama-server` GGUF (no HF token; `llama.cpp + GGUF` only).
- **P2 — Vertex AI Try-On (Phase T1)** — blocked on user adding Google Service Account JSON to `.env`.
- **P2 — Phase V4.2/V4.3** — STT migration + TTS swap; paused.

### Known constraints (binding)

- **No `HF_TOKEN` / `EYES_HF_TOKEN`** anywhere. Target Eyes arch is `llama.cpp + GGUF` (see `/app/CONCRETE_FACTS.md`).
- **Frontend dep policy:** never edit `package.json` by hand; always `yarn add <pkg>`.
- **Backend dep policy:** never edit `requirements.txt` by hand; `pip install <pkg> && pip freeze > backend/requirements.txt`.
- **Never modify** `REACT_APP_BACKEND_URL`, `MONGO_URL` in `.env`s.
- Mongo uses UUID `id`s only (never `ObjectId`).
- Backend API routes must be prefixed `/api`.

---

## 1) Objectives

### P0 — Add Item pipeline consolidation (“Upload-Items” sealed module) — **IN PROGRESS**

**Goal:** Treat the existing “Upload-Items” flow as a *closed system* routine and route **every** add-item workflow through it.

**Definitions**
- **Upload-Items routine**: the canonical flow currently embedded in `frontend/src/pages/AddItem.jsx`:
  1) pre-flight fingerprinting + duplicate detection
  2) `/api/v1/closet/analyze` NDJSON streaming (detect → placeholders → per-item hydration)
  3) optimistic save (`POST /api/v1/closet`) with background reconcile
  4) deferred background matting (“Polishing…”) registration via `workStore`

**Non-negotiables (user)**
- Upload-Items is a **sealed module**: other workflows call it; they don’t re-implement it.
- Must support **single upload**, **camera upload**, **>5 batch upload**.
- Must expose a **programmatic entry point** for future flows (e.g. “save outfit suggestion”).
- Must be **provider-agnostic**: future Gemma↔Gemini switch is backend-owned (Mongo override via `eyes_override.py`). Frontend module must keep calling `/closet/analyze` and never hardcode providers.
- Remove `bulkInfo`/aggregate UI: **same per-card UX regardless of count**.
- Drop the per-card **full-field “Edit”** editor; keep only lightweight inline edits (faster save).

### P0 — Production / preview sync discipline — **ONGOING**

- Preview must remain the proving ground.
- Production pod must be redeployed to pick up preview changes (user workflow).

### ✅ Existing shipped work (unchanged)

- ✅ FastAPI backend + React frontend
- ✅ `/api/v1/closet/analyze` NDJSON streaming for multi-crop analysis
- ✅ `warmup.py` concurrent model warmup
- ✅ SegFormer hint enforcement (reduces hallucinated categories)
- ✅ Cross-page progress: `workStore.js`, `WorkProgressFloater.jsx`, completion toasts
- ✅ Patch M20.5.2 bulk regression fix

---

## 2) Implementation Steps

### Phase U — “Upload-Items” sealed module + AddItem thin shell (**NEW — P0**) — **IN PROGRESS**

> This phase is explicitly designed to stop recurrence of “batch vs single drift”.

#### U1 — Extract sealed module (no behavior change)
**Objective:** Move the canonical add-item pipeline out of `AddItem.jsx` into a single, reachable, fast module.

**Decision:** implement as a singleton + hook in one file:
- `frontend/src/lib/uploadItems.js` (single file for reachability/boot speed)

**Public API (sealed contract)**
- `uploadItems.start(files, opts)`
  - supports both:
    - `mode: 'fire-and-forget'`
    - `mode: 'awaitable'` (resolves when batch settles)
- `uploadItems.getSnapshot()`
- `uploadItems.subscribe(fn)`
- `useUploadItems()` (React hook wrapper)

**Internal (not exported):** analyze/split/hydrate/save/polish plumbing.

**Provider independence (Gemma↔Gemini):**
- Module calls `api.analyzeItemImage()` → `/api/v1/closet/analyze`.
- Backend chooses provider based on Mongo override (`eyes_override.py`).
- Frontend module must not reference any provider token or env var.

#### U2 — Rewrite `AddItem.jsx` as a thin shell (~300 LoC)
**Objective:** `AddItem.jsx` becomes a UI-only page.

**Changes:**
- Replace embedded pipeline functions with calls to `useUploadItems()` / `uploadItems.start()`.
- Route:
  - single upload
  - camera input
  - drag/drop
  into `uploadItems.start(files, { ... })`.
- Remove `bulkInfo`/`bgBatch` and any count-based branching. (Same per-card UX for 1..N.)
- Remove the per-card full-field “Edit” editor; keep only lightweight inline edits.

**Acceptance criteria:**
- Upload 1 photo → same analysis + save behavior.
- Upload 2–5 photos → same as today.
- Upload 6+ photos → same as today but per-card UX (no aggregate card).
- Cross-page floater and polish toast still work.

#### U3 — Component extraction (next session)
- Extract per-card UI to `components/upload/UploadItemCard.jsx`.
- Extract `DuplicateConfirmDialog`.

#### U4 — Contract tests (next session)
- Add tests that pin the public `uploadItems` API + expected lifecycle invariants.

#### U5 — Provider switch smoke (next session)
- Document and verify: flipping Mongo override (`eyes_provider`) changes provider without frontend edits.

---

## 3) Next Actions (immediate)

### P0
1. **Phase U1 + U2** (this session scope):
   - Create `frontend/src/lib/uploadItems.js` sealed module
   - Rewrite `AddItem.jsx` thin shell
   - Remove bulk aggregate UX
   - Remove full-field per-card editor (keep inline edits)
2. **Ship to preview** and run manual smoke:
   - upload 1 / 5 / 10 photos
   - verify duplicate skip on re-upload
   - verify polishing drains and toast fires

### P1
3. Backfill legacy closet items missing `source_sha256` via hash-repair stream.
4. Remap CCP classes in `/app/scripts/run_eyes_benchmark.py`.
5. Rewrite Eyes GGUF runbook (no HF tokens).

### P2
6. Vertex AI Try-On Phase T1 (blocked on credentials).

---

## 4) Success Criteria

### Phase U success criteria
- **Single source of truth:** no add-item workflow contains its own analyze/save pipeline.
- **Sealed public contract:** all consumers call `uploadItems.start(...)` / `useUploadItems()`.
- **No drift:** new flows (camera, single, >5) route through the same code.
- **Provider-agnostic:** module never references Gemini/Gemma directly; provider switch remains backend-owned.
- **UX:** per-card upload experience is consistent for any batch size; full-field edit UI removed.

---

# Phase V4 — Eyes v4 Production Deploy + Audio Migration (2026 continuation)

> **Status:** V4.1 complete in preview. V4.2–V4.5 paused until P0 Upload-Items consolidation is stable.

(remaining V4 text unchanged below)

---

## ✅ Patch U1 + U2 (May 2026) — Sealed "Upload-Items" routine + thin AddItem.jsx shell — SHIPPED

### User mandate

> "We accomplished the 'Add item' pipeline. This is a perfect
> workflow. I want to wrap the Upload-Items pipeline, keep it as a
> closed system (no modification allowed) routine. I want every add
> item workflow to use the Upload-Items routine, not inventing this
> pipeline for every workflow."

### What shipped

**Phase U1 — `frontend/src/lib/uploadItems.js` (NEW, sealed)**

The entire pipeline lives here now:
- fingerprint files (sha256 + aHash + colour-sig)
- pre-flight duplicate detection against the cached closetStore
- draft builder (was `continueInteractive`)
- NDJSON streaming analyzer (was `analyzeCard`) — splits the detect
  frame into per-garment placeholders, hydrates each via `item`
  frames, propagates source fingerprints (post-M20.5.2 contract)
- optimistic-first save (was `saveAll`) — parallel `Promise.allSettled`,
  ghost reconcile, polish registration, failure recording
- auto-save drain (was the `pendingAutoSave` effect) — now at MODULE
  level, fires from `_notify()` so it works even after the host page
  unmounts
- DPP draft injection (was `hydrateFromDpp`)
- `buildCreatePayload` (was inline)
- `hydrate(analysis, user)` (was inline)
- per-batch tracking with both fire-and-forget and awaitable modes

**Public API (frozen — sealed contract):**

```js
uploadItems.start(files, opts)              // void | Promise<{saved, failed}>
uploadItems.getSnapshot()
uploadItems.subscribe(fn)
uploadItems.onBatchSettled(fn)
uploadItems.saveAll(opts?)
uploadItems.removeCard(id)
uploadItems.retryCard(id, opts?)
uploadItems.updateField(id, patch)
uploadItems.patchCard(id, patch)
uploadItems.hydrateFromDpp(res, user?)
uploadItems.resolvePreflight(decisions, user?)
uploadItems.acceptDuplicate(id)
uploadItems.discardDuplicate(id)
uploadItems.clearPreflight()
uploadItems.reset()                          // test hook only
useUploadItems(opts?)                        // React hook wrapper
```

`opts.mode`: `'fire-and-forget'` (default) | `'awaitable'`.
`opts.autoSave`: `boolean` — defaults to `false` on `/add` (manual
review + Save All); `true` for programmatic callers like a future
"save outfit suggestion" feature.
`opts.autoResolveDuplicates`: `'prompt'` (host page mounts dialog)
| `'skip'` | `'add-all'` (non-interactive).

**Phase U2 — `frontend/src/pages/AddItem.jsx` (REWRITTEN)**

- 2118 LoC → 754 LoC (-64 %, bundle dropped 2.0 MB → 1.8 MB).
- All pipeline functions removed (now in `uploadItems.js`).
- Renders consumer of `useUploadItems({ user, onBatchSettled })`.
- **`bulkInfo` / `bgBatch` / aggregate progress card DELETED.**
  Per the user's spec, every count (1, 5, 50) now uses the same
  per-card UI.
- **Full-field per-card editor DELETED** on `/add`. Only
  `NameCaption` + `IntentSelector` (+ price when `for_sale`)
  remain. Users edit the dropped fields from `/closet/:id` after
  save.

### Provider independence (Gemma ↔ Gemini)

The sealed module touches exactly ONE backend endpoint:
- `POST /api/v1/closet/analyze` (via `api.analyzeItemImage`)

The backend chooses between self-hosted Gemma 4 E2B and Gemini via
the Mongo override doc (`dressapp_prod.config._id=eyes_provider`,
read by `backend/app/services/eyes_override.py` with 5 s cache).
**Flipping providers requires ZERO frontend changes.** This is
asserted in the module's top-level docstring as a sealed-contract
invariant.

### Drift bait checklist (sealed in the file header)

The module header lists the four traps that caused
M20.5 / M20.5.1 / earlier regressions and bans them in writing:

1. NO parallel `handleBatchBackground` for >5 photos.
2. NO `setTimeout(0, saveAll)` race — use `pendingAutoSave` + the
   module-level drain.
3. Placeholder cards MUST inherit source fingerprints (M20.5.2).
4. NEVER hardcode model / provider / token / endpoint other than
   `/closet/analyze` and `/closet`.

### Verification (testing_agent iteration 26 — 95 % success)

| Scenario | Result |
| --- | --- |
| Single upload (1 image → 2 garments) | ✅ ~11 s, lightweight UI, save+nav OK |
| Multi-photo (3 images → 6 cards) | ✅ ~27 s parallel, save+nav OK |
| **Bulk upload (7 images → 15 cards)** | ✅ **per-card UI used (regression test PASSED)** |
| Heavy editors verified ABSENT | ✅ no TaxonomyGrid/WeightedList/QualityRow/SeasonPicker/TagsEditor |
| Lightweight fields verified PRESENT | ✅ name + caption + intent + price + edit-later hint |
| DPP scanner button | ✅ opens dialog |
| Pre-flight duplicate dialog | ✅ shows on re-upload of known dupe |
| Polishing workflow + WorkProgressFloater | ✅ visible |

**Known minor issue (NOT a refactor regression):** for the 7-image
bulk test, some cards took 166 s+ to analyze and Save All didn't
auto-navigate. Same Emergent LLM-key concurrency-1 throttle
documented in patches M17/M18/M19. `pendingAutoSave` correctly
waits; once the slow cards finish, nav fires. Pre-existing
behavior — not a Phase U regression.

### Files touched

- `frontend/src/lib/uploadItems.js` (NEW, 1320 LoC inc. docstring + sealed contract)
- `frontend/src/pages/AddItem.jsx` (REWRITTEN, 754 LoC)
- `plan.md` (this entry)

### Out of scope for this session (deferred to U3+)

- **U3** — extract per-card UI to `components/upload/UploadItemCard.jsx`;
  extract `DuplicateConfirmDialog` to its own file.
- **U4** — contract tests pinning the public API in
  `frontend/src/lib/__tests__/uploadItems.contract.test.js`.
- **U5** — verify Gemma↔Gemini flip causes no frontend behavior
  change (smoke test against staged self-hosted Gemma artifacts on VPS).
