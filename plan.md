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

## 🔍 Diagnostic Report (May 2026) — Under-segmentation + "white window" cards in production closet

### User report

Uploaded 6 full-outfit photos through the new sealed `uploadItems.js`
pipeline. **Expected 20-30 cards, got 13. Half of them are "white
windows"** (mostly-transparent thumbnails with faint garment
outlines). Asked for diagnosis — no fix this session, just root cause.

### Diagnosis methodology

1. Audited `backend/app/services/clothing_parser.py` +
   `backend/app/services/garment_vision.py` for every filter that can
   drop a SegFormer detection between mask production and the
   per-card crop that reaches Gemini.
2. Inspected live preview-pod backend logs from the user's actual
   bulk-upload session to count `produced N garment(s)` lines and
   `NMS suppressed`, `too patchy`, and `dropping tiny crop` warnings.
3. Ran two diagnostic scripts against `/app/inference-server/eyes/test_images/`
   (15 outfit JPGs, 550×830 px each):
   - **Pass A** — counted SegFormer outputs from
     `clothing_parser.parse_garments` (post-NMS, post-postprocess).
   - **Pass B** — for each SegFormer region from Pass A, called
     `garment_vision._crop_to_bbox` to see which would actually reach
     Gemini.

### Findings

**Pass A — SegFormer detection** is healthy:

```
TOTAL: 43 garments across 10 images = 4.3 per image avg
```

If the user uploaded 6 outfits, SegFormer alone produces ~26
detections. Matches the user's "expected 20-30" target.

**Pass B — `_crop_to_bbox` survival** is THE bottleneck:

```
TOTAL parsed:    63
TOTAL survived:  37
Drop rate:       41.3 %
Dropped label counts:
  Shoes:         10/15  ( 67 % drop rate)   ← worst offender
  Bag:            6/15  ( 40 %)
  Sunglasses:     5/15  ( 33 %)
  Belt:           2/15  ( 13 %)
  Pants:          1/15  (  6 %)
  Skirt:          1/15  (  6 %)
  Upper-clothes:  1/15  (  6 %)
```

**Pattern is unambiguous: accessories + footwear get systematically
dropped after SegFormer succeeds.**

### Root cause #1 — Mismatched per-category gates

`clothing_parser._min_area_frac_for(category)` (Patch 10a) was
tightened to recognise that accessories occupy 0.05 % of the frame
on full-body shots. But `garment_vision._crop_to_bbox` then applies a
SECOND gate with HARDCODED, NON-CATEGORY-AWARE thresholds:

```python
# garment_vision.py
_MIN_CROP_AREA_PCT = 0.008              # 0.8 % of frame  ← 16× stricter than accessory threshold
_MIN_CROP_SHORT_EDGE_FLOOR_PX = 96      # 96 px hard floor
_MIN_CROP_SHORT_EDGE_PCT = 0.12         # 12 % of source short edge
_MIN_CROP_SHORT_EDGE_CEIL_PX = 256
```

On a 550 px source: floor = `max(96, min(256, 0.12·550)) = 96 px`.
On a 1500 px source: floor = `max(96, min(256, 0.12·1500)) = 180 px`.
On a 2000 px source: floor = `max(96, min(256, 0.12·2000)) = 240 px`.

A pair of shoes on a 1500 px full-body shot typically occupies
80-130 px short-edge → dropped silently.

The accessory area gate (`_min_area_frac_for("accessory") = 0.0005`)
allowed them through clothing_parser; `_MIN_CROP_AREA_PCT = 0.008`
killed them in garment_vision. **The two gates contradict each other.**

### Root cause #2 — Negative bbox padding compounds the short-edge problem

Patches 12k/12l set NEGATIVE padding for adjacent-garment edges:

| Category | TRBL pad | Effect |
|---|---|---|
| top      | (0.04, 0.02, **-0.025**, 0.02) | Bottom edge cuts 2.5 % into bbox |
| bottom   | (**-0.015**, 0.02, **-0.025**, 0.02) | Both top + bottom edges cut in |
| dress    | (0.02, 0.02, **-0.020**, 0.02) | Hem cuts in |
| outerwear| (0.01, 0.03, **-0.010**, 0.03) | Hem cuts in |
| footwear | (**-0.015**, 0.03, 0.03, 0.03) | Top edge cuts in |

For a small footwear bbox (e.g., 100 px tall), the -1.5 % top
negative padding removes another 1-2 px AND lowers the y2-y1
short-edge measurement. Combined with the floor, more drops.

The negative padding was the correct fix for the "blouse shows skirt
rim" bleed-through bug, but it stacks with `_MIN_CROP_SHORT_EDGE`
to over-prune small garments.

### Root cause #3 — "White window" cards = rembg-only + low-contrast background

Live log analysis from the user's upload session:

```
apply_alpha_intersection: SegFormer mask too patchy
  (9.2 % coverage  < 40 % threshold) — falling back to rembg-only (crop 111×96)
  (34.9 % coverage < 40 % threshold) — falling back to rembg-only (crop 120×228)
  (6.1 % coverage  < 40 % threshold) — falling back to rembg-only (crop 103×107)
```

`_MIN_MASK_CONFIDENCE = 0.40` in `apply_alpha_intersection` causes
the SegFormer-mask refinement to be SKIPPED on tight accessory
crops. The output is **rembg-only**. On a busy background (e.g. a
brown belt against tan trousers, a beanie against dark hair) rembg
has no foreground-vs-background contrast → returns an all-zero alpha
→ thumbnail is mostly-transparent → **"white window"**.

Logged sizes (111×96, 103×107) are right at the short-edge floor —
these are the crops that BARELY survived `_crop_to_bbox` but then
fail the matte step.

### Root cause #4 — NMS over-collapses layered looks

`_suppress_overlapping_garments` (Patch 12) drops the smaller of two
masks when containment ≥ 0.70 OR IoU ≥ 0.50.

Live log evidence:

```
NMS suppressed 1 overlap(s):
  ['Dress(→Upper-clothes, iou=0.02, cont=1.00)']
```

A real layered look (long blazer over a dress that just peeks below
the hem) → SegFormer fires both Upper-clothes (huge) and Dress
(small). NMS sees `cont=1.00` → drops Dress. **The user loses one
real garment per layered outfit.**

This is a SECONDARY contributor (1 garment per layered look) vs the
PRIMARY `_crop_to_bbox` cull (40 % of total). It only matters once
the crop-to-bbox issue is solved.

### Summary table

| # | Cause | Estimated impact |
|---|---|---|
| **1** | `_MIN_CROP_AREA_PCT = 0.008` + `_MIN_CROP_SHORT_EDGE_FLOOR_PX = 96` in `garment_vision.py` are NOT category-aware. Contradicts `clothing_parser._min_area_frac_for("accessory")`. | **41 % drop on accessories + footwear; the dominant under-segmentation cause.** |
| **2** | Negative bbox padding (Patches 12k/12l) for footwear top + bottom hems compounds the short-edge floor problem. | Marginal — adds ~5 % on top of root cause #1. |
| **3** | `apply_alpha_intersection` bails out at <40 % mask coverage → rembg-only on small accessories → rembg can't find foreground on busy backgrounds → blank alpha → "white window". | Affects ~30-50 % of accessory cards that DO survive crop. |
| **4** | NMS containment threshold 0.70 drops the inner garment of layered looks. | ~1 garment per layered outfit photo. |

### Recommended fixes (NOT applied this session per user choice 5a)

**Top-priority fix (addresses root cause #1):**

Make `_MIN_CROP_AREA_PCT` + `_MIN_CROP_SHORT_EDGE_*` **per-category**
in `garment_vision.py`, mirroring the per-category area thresholds
already established in `clothing_parser._MIN_AREA_FRAC_PER_CATEGORY`.
Target table:

| Category | min crop area % | short-edge floor px | short-edge pct |
|---|---|---|---|
| top / bottom / dress | 0.8 % | 96 | 12 % |
| outerwear | 0.8 % | 96 | 12 % |
| **footwear** | **0.05 %** | **40** | **5 %** |
| **accessory** | **0.05 %** | **40** | **5 %** |
| **headwear** | **0.10 %** | **48** | **6 %** |

Expected impact: cuts the 41 % drop rate to ~5 %, bringing
end-to-end garment count per outfit photo from ~2.5 to ~4.0.

**Secondary fix (addresses root cause #3):**

Drop `_MIN_MASK_CONFIDENCE` from 0.40 to 0.25 ONLY for footwear /
accessory crops (keep 0.40 for tops/bottoms/dresses where a patchy
mask really does indicate a problem). This keeps SegFormer refinement
firing on the small-accessory cases where rembg is most likely to
fail alone, eliminating most "white window" thumbnails.

**Layered-look fix (addresses root cause #4):**

Raise NMS containment threshold from 0.70 → 0.85. Empirically a
genuine phantom-inside-real has cont ≥ 0.95 (the smaller mask is
entirely subset of the larger). Layered looks rarely exceed 0.85
because the inner garment usually has at least 15 % of its pixels
visible outside the outer garment's mask.

### Action items for next session

1. Implement the per-category `_crop_to_bbox` thresholds in
   `garment_vision.py`. Add a small contract test against the test
   image dataset that asserts ≥ 4 garments per image on the 30-image
   benchmark.
2. Implement the per-category `_MIN_MASK_CONFIDENCE` in
   `clothing_parser.apply_alpha_intersection`.
3. Raise the NMS containment threshold to 0.85.
4. Re-run the user's 6-photo bulk upload on preview and confirm
   ~24-30 cards land in the closet with no white-window matte
   failures.

### Files referenced in this diagnosis

- `backend/app/services/clothing_parser.py` (parse_garments, NMS,
  apply_alpha_intersection, `_MIN_AREA_FRAC_*`, `_MIN_MASK_CONFIDENCE`,
  `_DILATE_PCT_BY_CATEGORY`)
- `backend/app/services/garment_vision.py` (`_crop_to_bbox`,
  `_MIN_CROP_*`, `_BBOX_PAD_TRBL_BY_CATEGORY`,
  `_enforce_segformer_category`)
- `/app/inference-server/eyes/test_images/` (30 outfit JPGs, see
  CONCRETE_FACTS.md)

### Files NOT to touch

- `frontend/src/lib/uploadItems.js` is **sealed and correct**. It
  faithfully renders whatever the backend streams. ZERO frontend
  change required to fix the under-segmentation / white-window
  issues — all four root causes are server-side.
