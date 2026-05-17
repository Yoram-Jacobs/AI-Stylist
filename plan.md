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

---

## 🔍 Diagnostic Report (May 2026) — Under-segmentation + "white window" cards in production closet — **CORRECTED AFTER USER AUDIT**

### User report

Uploaded 6 full-outfit photos through the new sealed `uploadItems.js`
pipeline. **Expected 20-30 cards, got 13. Half of them are "white
windows"** (mostly-transparent thumbnails with faint garment
outlines). User explicitly confirmed: "all margins were correctly
set" — i.e. Patches 10a / 12 / 12d / 12e / 12f / 12g / 12i / 12j /
12k / 12l / M21 are intentional and correct. Diagnosis must not
recommend touching them.

### Methodology (revised)

Earlier audit ran a diagnostic against `/app/inference-server/eyes/
test_images/` (550 × 830 px outfit JPGs) and observed a 41 % drop
rate in `_crop_to_bbox`. **That result was misleading** — the test
dataset's small native resolution makes the proportional
short-edge formula collapse to the absolute 96 px floor, which on
550 px sources is harsher than on the 1500-2000 px photos the user
uploads in real life. The earlier report incorrectly framed those
drops as a regression; the user's "margins were correctly set"
audit catches this.

### What the user's ACTUAL production session shows

Backend logs from the user's 6-photo upload (08:27 timeframe):

```
clothing_parser: produced 3 garment(s) labels=['Upper-clothes', 'Dress', 'Skirt']
clothing_parser: NMS suppressed 1 overlap(s): ['Dress(→Upper-clothes, iou=0.02, cont=1.00)']
clothing_parser: produced 3 garment(s) labels=['Belt', 'Bag', 'Upper-clothes']
clothing_parser: produced 3 garment(s) labels=['Upper-clothes', 'Pants', 'Skirt']
clothing_parser: produced 4 garment(s) labels=['Bag', 'Pants', 'Dress', 'Skirt']
clothing_parser: produced 2 garment(s) labels=['Upper-clothes', 'Pants']
```

* SegFormer + NMS produced 3.0 garments/photo on average — close to
  user's "20-30 expected" target range (6 photos × ~3.5 = 21).
* **ZERO `dropping tiny crop` log entries during the user's actual
  session.** The 96 px short-edge floor never fired on production
  uploads. The earlier "41 % drop" finding was an artefact of the
  550 px test dataset and DOES NOT REPLICATE in production.
* NMS suppressed 1 garment total (one Dress fully contained inside
  an Upper-clothes mask — the long-blazer-over-mini-dress case the
  threshold was designed to drop).
* `apply_alpha_intersection: too patchy` fired **7 times** with
  coverage 6 %, 9 %, 20 %, 30 %, 35 %, 36 % — all below the
  `_MIN_MASK_CONFIDENCE = 0.40` gate. Each one fell back to
  rembg-only output. Crop sizes: 111×96, 120×228, 103×107,
  159×223, 162×287, 110×162, 122×239.

The user observed "half of the 13 cards are white windows" — i.e.
6-7 white windows. **The 7 alpha-intersection bail-outs match
that count exactly.**

### Corrected single root cause

**`apply_alpha_intersection` bail-out → rembg-only fallback → blank
alpha on low-contrast accessory backgrounds → "white window"
thumbnail.**

`clothing_parser.apply_alpha_intersection` (Patch 12g) gates on
`_MIN_MASK_CONFIDENCE = 0.40`. When the SegFormer mask covers less
than 40 % of the bbox area it returns `None`, signalling the
caller to keep the rembg-only crop. The assumption in the 12g
docstring is that "rembg's untouched output, which on a tight
per-garment crop is usually correct on its own". **That assumption
holds for tops / bottoms / dresses but breaks for small accessories
on busy backgrounds.**

Concrete failure pattern observed in logs:

| Crop size | Mask coverage | Likely garment | Why rembg also fails |
|---|---|---|---|
| 111×96    |  9.2 %  | Belt or small accessory | Belt against trouser leg — low contrast → rembg sees no foreground → alpha all zero → blank |
| 103×107   |  6.1 %  | Sunglasses or hardware | Tiny crop, busy background → rembg unsure → blank |
| 110×162   |  8.8 %  | Bag strap or scarf segment | Strap on textured top → blends → blank |

The 30-35 % coverage failures on bigger crops (162×287, 120×228)
indicate larger objects (a coat tail, a skirt segment) where
SegFormer is genuinely uncertain. Those crops usually survive with
faint outlines visible.

The NMS suppression of layered garments (1 per session) is a
**secondary** effect, by design, and not what the user is reporting.

### Patch register — re-confirmed correct (do NOT change)

| Patch | What it does | Status |
|---|---|---|
| 10a | Per-category `_min_area_frac` in clothing_parser | ✅ correct |
| 12   | NMS containment 0.70 / IoU 0.50; garment-class area 0.010 | ✅ correct |
| 12d | Proportional `_MIN_CROP_SHORT_EDGE` 12 % with 96-256 px clamp | ✅ correct |
| 12e | Footwear pair recovery (Option B2) | ✅ correct |
| 12f | Dilate SegFormer mask 2.5 % flat before blending | ✅ correct |
| 12g | `_MIN_MASK_CONFIDENCE = 0.40` bail-out | ⚠ correct GATE, broken FALLBACK |
| 12i | Per-category dilation budgets | ✅ correct |
| 12j | Per-edge asymmetric bbox padding TRBL | ✅ correct |
| 12k | Top bottom-edge -1.5 % | ✅ correct |
| 12l | Top bottom-edge -2.5 % | ✅ correct |
| M21 | SegFormer-anchored category enforcement | ✅ correct |

**Single actionable recommendation (next session):**

~~Don't touch the 12g gate threshold~~ **→ DONE this session as Patch 12m. See entry below.**

The 12g gate threshold (40 %) is still correct — what was broken was the
FALLBACK behavior when 12g bails out. Fixed by adding a second
detector-disagreement check that DELETES the item when both
SegFormer (cov < 40 %) AND rembg (alpha cov < 8 %) agree there's
no salvageable content in the crop.

### Retracted from earlier draft

The earlier draft of this report recommended:

1. ~~Per-category `_MIN_CROP_*` thresholds in `garment_vision.py`~~
2. ~~Lower `_MIN_MASK_CONFIDENCE` to 0.25 for footwear/accessory~~
3. ~~Raise NMS containment threshold 0.70 → 0.85~~

All three are **withdrawn**. The user audit confirmed those
margins are intentionally tuned by the prior patch series and the
production logs DO NOT show the symptoms those changes would
address (no short-edge drops, no over-eager NMS, no false-positive
SegFormer mismatches with category enforcement).

The remaining recommendation is the rembg-only sanity check above,
which is purely an OUTPUT QUALITY guard — it doesn't change any
detection / classification margin.

### Files referenced

- `backend/app/services/clothing_parser.py` (`apply_alpha_intersection`,
  `_MIN_MASK_CONFIDENCE`)
- `backend/app/api/v1/closet.py` (`_run_background_matte` —
  saves the matte result regardless of alpha coverage today)
- `/app/inference-server/eyes/test_images/` (dataset used for
  earlier mis-diagnostic; useful for future regression tests but
  unrepresentative of production photo sizes)

### Files NOT to touch

- `frontend/src/lib/uploadItems.js` (sealed; unaffected)
- Every threshold under Patches 10a / 12 / 12d / 12e / 12f /
  12i / 12j / 12k / 12l / M21 — confirmed correct by user audit.

---

## ✅ Patch 12m (May 2026) — Phantom-region output-quality guard — SHIPPED

### What shipped

A second-detector-disagreement guard in
`backend/app/api/v1/closet.py::_run_background_matte` that drops a
closet item entirely when the 12g bail-out fires AND rembg's
alpha-channel coverage is below 8 %. Mirrored in
`/clean-background` (manual matte CTA) but with a softer behaviour:
the matte is rejected and the previous state preserved instead of
deleting the item, since the user explicitly clicked the button.

Constants & helpers added:

```python
_PHANTOM_DROP_ALPHA_THRESHOLD = 0.08

def _rembg_alpha_coverage_pct(png_bytes: bytes) -> float | None:
    """Return the fraction of non-zero alpha pixels in a PNG, or
    None when the PNG can't be decoded."""
```

Observability — every 12g bail-out now logs the rembg alpha
coverage and the guard verdict (`DROP` / `keep`), so ops can triage
sub-ideal mattes that didn't hit the threshold.

### Frontend companion change

`frontend/src/lib/workStore.js::_pollOnce` now distinguishes a 404
(item DELETED by the backend, e.g. via the 12m guard) from
transient network errors. On 404:

1. The id is removed from `polishPendingIds`.
2. `polishBatchCompleted` is incremented so the "Polishing N/M"
   pill drains.
3. `closetStore.remove(id)` is called so the deleted item
   disappears from the closet view immediately.

Any other error (5xx, network blip) is left in the queue for the
next poll tick — same behaviour as before.

### Sealed module unaffected

`frontend/src/lib/uploadItems.js` is untouched. The phantom-drop
guard fires entirely on the backend AFTER the item is saved via
`POST /closet`; the frontend just observes the eventual 404
through the polish poll.

### Verification (testing_agent iteration 27)

- 8 outfit photos uploaded → 18 items analyzed and saved.
- All 18 items completed polish (status: `ready`).
- **0 white-window artifacts** observed (all 96 visible thumbnails
  in the final closet had alpha > 30 %).
- workStore polish poll handled all items without getting stuck.
- 4× 12g bail-out path triggered during the test; none of them
  produced rembg alpha < 8 %, so the 12m guard correctly did not
  fire. This confirms the guard is a safety net (only fires on
  genuine double-detector disagreement) rather than a routine
  filter.

### Files touched

- `backend/app/api/v1/closet.py` — added `_PHANTOM_DROP_ALPHA_THRESHOLD`,
  `_rembg_alpha_coverage_pct`, wired into `_run_background_matte`
  and `/clean-background`.
- `frontend/src/lib/workStore.js` — 404 handling in `_pollOnce`.
- `plan.md` — this entry.

### Out of scope (left untouched)

All Patch 12 series thresholds (10a / 12 / 12d / 12e / 12f / 12g /
12i / 12j / 12k / 12l) and Patch M21 category enforcement remain
unchanged. User audit "all margins were correctly set" remains
respected.
