# GarmentVisionWaste — The May 2026 regression & recovery

> **Window covered:** 16 May 2026 01:14 → 17 May 2026 (this session).  
> **Subject:** How the `garment_vision` pipeline got corrupted by an over-eager refactor, what it cost, and how it was rebuilt — surgically, with the user's working `AddItem.jsx` left untouched.  
> **Why this file exists:** Future agents need to know that "refactoring `AddItem.jsx` to share the GOLD pipeline" is a documented failure mode. Do not repeat it.

---

## 1. The regression

A prior agent (between 16 May 01:14 and the hard-reset point) was asked to share the **GOLD batched pipeline** (2–5 photos with progressive NDJSON streaming) with the Camera, Single-photo, and Batch-upload flows in `AddItem.jsx`. Instead of a surgical change, the agent:

* refactored the monolithic `AddItem.jsx` (~2 265 LoC), breaking the working GOLD path,
* "poisoned" `plan.md` and `CONCRETE_FACTS.md` with sprawling patch logs,
* introduced cosmetic frontend changes the user had not asked for, and
* did **not** fix the symptoms the user had actually reported (face / body leaks into garment crops, phantom empty cards, dropped accessories).

The user — visibly out of patience — demanded a **hard reset to commit `fe45ba9`**, wiping every change the agent had made and restoring the original AddItem.jsx + the pre-corruption docs.

From that baseline, the recovery work began. **The frontend was never touched again** for the duration of the recovery. Every fix was a backend-only, surgical change to `garment_vision.py` / `clothing_parser.py`.

---

## 2. Recovery summary (one paragraph)

After the hard reset, the user reported six independent symptoms in the AddItem pipeline, mostly visible in the closet grid: (1) skin / face / hair leaking into garment crops; (2) phantom empty cards (white tiles) saved to the closet when rembg returned nothing; (3) small shoes / accessories silently dropped by an absolute-pixel floor; (4) bags fragmenting into two cards because their masks were disconnected; (5) the 6-item cap dropping legitimate accessories instead of preserving one item per kind; and finally (6) crop sizes wildly variable in the closet grid — sometimes tiny dots, sometimes overflowing — because `crop_base64` left the backend at the raw rembg resolution. Each was addressed with a single, targeted backend patch (fixes A–D, geometric head exclusion, category-aware percentage floors, mask-fragment bridging, category-aware cap ordering, and finally `_fit_crop_to_card`). Lint stayed clean throughout, the backend restarted cleanly on each iteration, and the frontend was untouched.

---

## 3. Timeline & action table

> Times are approximate (chat ranges, not log timestamps). Each row corresponds to one user prompt + the agent's response.

| Timeline (approx.) | User prompt (verbatim or paraphrased) | Action taken |
|---|---|---|
| 16 May, 01:14 → ~02:00 | "Share the GOLD 2–5 batch pipeline with the Camera / Single-photo / Batch flows in `AddItem.jsx`." (to prior agent) | Prior agent over-refactored `AddItem.jsx`, broke the GOLD path, bloated `plan.md` / `CONCRETE_FACTS.md` with patch logs. |
| ~02:00–03:00 | "You corrupted the frontend and the docs. Hard-reset the repository to `fe45ba9`." | **Hard reset to `fe45ba9`.** Frontend + docs restored. Agent acknowledged the lesson: surgical changes only; no docs bloat without permission. |
| ~03:00 | "Faces and limbs are leaking into garment crops. Phantom empty cards keep showing up. Fix the alignment first." | **Fix A** — corrected mask/bbox alignment in `_bbox_crop_useful`: the SegFormer mask is now sliced from the **exact** rectangle the JPEG was cut at (`box_px`) instead of a separately-computed bbox. Up-to-5 % shift on asymmetric-padding categories eliminated. |
| ~03:30 | "Empty white cards still appear in the closet." | **Fix B** — added a **5 % solid-alpha phantom guard** in `_matte_crops`. Final RGBA matte's alpha-≥-128 ratio is measured; if `< 5 %`, the detection is dropped entirely. Empty-card UX gone. |
| ~04:00 | "Two layered tops collapse into one bbox. Split them." | **Fix C** — connected-component split: same-class detections are spatially grouped (via mask connected components); one detection emitted per spatial group. Two black T-shirts side by side no longer merge. |
| ~04:30 | "Faces / hair / arms are still leaking into garment matters." | **Fix D** — built an explicit human-skin / hair / face mask from SegFormer's person classes, dilated it, and **subtracted** it from the soft mask post-dilation in `apply_alpha_intersection`. Cheap when present, no-op when absent. |
| ~05:00 | "One image still shows the face + sunglasses on a top card." | **Geometric head-exclusion** added for tops / outerwear / dresses: the band above the estimated shoulder line is forced to alpha=0 regardless of what SegFormer / rembg agree on. The remaining facial leak is gone. |
| ~05:30 | "Shoes and small accessories keep getting dropped." | **Replaced the absolute-pixel floor** in `_crop_to_bbox` with a **category-aware percentage short-edge floor** (`_resolve_min_short_edge_pct_for_category`). Footwear / accessories survive at 8 % of source short edge; tops require 18 %. Resolution-invariant — a shoe at 8 % of frame is accepted whether the upload is 550 px or 4 K. |
| ~06:00 | "This bag came back as two separate cards." | **Mask-fragment bridging** for accessories / bags: morphological closing + convex-hull bridge to re-join disconnected mask components within the same detection's bbox. Body + strap now one item. |
| ~06:30 | "Six-item cap is dropping the legitimate shoes. Why?" | **Category-aware ordering** before the cap: `_filter_useful_detections` now guarantees one item per kind survives before filling remaining slots with the next-largest area-ranked candidates. Footwear no longer evicted by three tops. |
| 17 May, ~current session start | "Small item crops are upscaled by backend processing and break the frontend card UI because the frontend does not downscale. Add a function to catch, rescale, and center upscaled crops to fit the card window." | Added **`_fit_crop_to_card(crop_bytes, crop_mime)`** in `garment_vision.py`. Initial implementation: scale-to-fit-or-shrink, never upscale; center on a 900×1200 (3:4) canvas. Wired at all 5 base64-emit sites. Unit-verified (6 cases) and backend restarted clean. |
| 17 May, ~30 min later | "Now we have the opposite issue — items show up as tiny dots in the closet. Modify the function to scale UP to fit the card window. E.g. shoe 25×120 → 250×1200, then center." | Updated `_fit_crop_to_card`: **removed the `, 1.0` upscale cap** so the helper now scales any crop to fit the canvas in either direction. Re-verified with the user's exact 25×120 → 250×1200 example (10× upscale, centered at x=325). All 6 test cases still pass. Backend restarted clean. |
| 17 May, this prompt | "This phase has concluded. (1) Update the documentation. (2) Create `GarmentVision.md`. (3) Create `GarmentVisionWaste.md` with a timeline / prompt / action table." | Created `docs/GarmentVision.md` (full pipeline reference), `docs/GarmentVisionWaste.md` (this file), added a concise recovery entry to `plan.md`, and a release note to `CHANGELOG.md`. |

---

## 4. Cost of the regression (what got wasted)

| Resource | Approx. cost |
|---|---|
| Wall-clock | ~5 hours of recovery work that would not have been needed if the prior agent had made the requested surgical change. |
| Code | One full hard reset (no salvage) — every line the prior agent wrote between 01:14 and the reset was discarded. |
| Trust | The user explicitly added a guardrail: future agents must not over-refactor `AddItem.jsx`, must not pad `plan.md` / `CONCRETE_FACTS.md` with verbose logs, and must keep changes backend-focused unless explicitly told otherwise. |
| Opportunity | The Vertex AI Try-On work (Phase T1) and the CCP benchmark remap (Phase Eyes / Eval) remained blocked the whole time because backend bandwidth was burnt on recovery. |

---

## 5. What stayed clean throughout

* **`frontend/src/pages/AddItem.jsx`** — not touched after the hard reset. The GOLD pipeline that the user had working remained intact.
* **`plan.md`** — no log bloat. Only this short recovery entry will be appended.
* **`CONCRETE_FACTS.md`** — not edited. The user's explicit instruction was honoured.
* **Ruff lint + backend service status** — green after every patch.
* **Test reports** — every fix had a `/tmp/test_*.py` python verification (no testing-agent ceremony, per the user's preference for fast surgical iterations).

---

## 6. Lessons (binding on future agents)

1. **Surgical over sweeping.** Every problem in the recovery list was fixed by editing one file (`garment_vision.py` or `clothing_parser.py`), no signature changes, no cross-module rewires. Bias toward the smallest possible diff that solves the symptom.
2. **`AddItem.jsx` is load-bearing.** The user has explicitly reverted at least one refactor of it. Treat it as read-only unless the user names the file and the change. If a backend fix can replace a frontend change, prefer the backend fix.
3. **Don't pad `plan.md`.** Patch logs belong in code comments and CHANGELOG. `plan.md` is a strategic blueprint, not a diary.
4. **`/api/v1/closet/analyze` is the bottleneck for every closet entry path.** Camera, single upload, batch upload, Chrome extension — they all funnel through it. A backend change there reaches every UI flow.
5. **Manual python verification beats heavy testing-agent runs for surgical patches.** A `python -c` or short script that exercises the helper directly is faster than spinning up Playwright for a one-line change.
