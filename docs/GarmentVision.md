# GarmentVision — The DressApp Eyes Pipeline

> **Module:** `backend/app/services/garment_vision.py`  
> **Companion module:** `backend/app/services/clothing_parser.py`  
> **Status:** Production (live on preview + `dressapp-eyes` self-host).  
> **Owner role:** Turns a single photo of a person (or a flat-lay) into N clean, individually-tagged closet items. Everything downstream — the closet grid, the stylist, the marketplace listings — assumes GarmentVision did its job.

---

## 1. Why GarmentVision exists

Every other product surface in DressApp is downstream of "what is in this photo?".

| Surface | Depends on GarmentVision for |
|---|---|
| **Closet (Add Item)** | Detects N garments in one upload, returns one card per item with bbox + clean cutout + 18-field analysis (item_type, sub_category, color, dress_code, season, …). |
| **Closet grid / list** | The per-item `crop_base64` and `clean_image_url` that GarmentVision emits are what the user sees as their card thumbnails. |
| **Stylist** | Reasons over the per-item analysis JSON (silhouette, fabric, color, dress_code). Garbage in → garbage out. |
| **Marketplace** | Auto-fills the listing form from the same analysis JSON (title, color, condition hint, category). |
| **Outfit reconstruction (Nano Banana "Repair photo" CTA)** | Takes GarmentVision's bbox crop + analysis as the conditioning input for image regeneration. |
| **Eyes self-host (Hetzner)** | The whole reason the `dressapp-eyes` Docker container + GGUF model exists is to serve this pipeline cheaply at scale. |

If GarmentVision drops an item, the user has to add it manually. If it leaks the wrong pixels into a crop, every downstream classifier learns the wrong color / silhouette. If it ships a phantom (empty) card, the user has to delete it. So the pipeline is **load-bearing**, and most of the patch history in `plan.md` is GarmentVision hardening.

---

## 2. Pipeline overview

```
                           ┌─────────────────────────┐
                           │   user uploads photo    │
                           └──────────┬──────────────┘
                                      │ bytes
                                      ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                       detect_items()                              │
       │                                                                   │
       │  1) SegFormer (b3_clothes, 18 classes) →                          │
       │       per-pixel semantic mask + per-class bbox                    │
       │       (clothing_parser.parse_garments)                            │
       │                                                                   │
       │  2) Human-skin / hair / face mask subtraction                     │
       │       (face & limb pixels surfaced, dilated, then SUBTRACTED      │
       │        from every garment mask)                                   │
       │                                                                   │
       │  3) Geometric head-exclusion for tops/outerwear/dresses           │
       │       (vertical band above the shoulder is forced to 0)           │
       │                                                                   │
       │  4) Spatial-group split (same-class collisions)                   │
       │       (one SegFormer class can hold two physical garments —       │
       │        connected-component analysis separates them)               │
       │                                                                   │
       │  5) Mask-fragment bridging for accessories                        │
       │       (a strap separated from a bag body gets re-joined)          │
       └──────────┬───────────────────────────────────────────────────────┘
                  │ list[detection: {bbox, kind, mask, label}]
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                  _filter_useful_detections()                      │
       │                                                                   │
       │  • Drop ≥90 %-of-frame detections (=> "analyse whole photo")     │
       │  • Apply category-aware ordering (guarantee 1 per kind first)    │
       │  • Cap at max_items                                               │
       └──────────┬───────────────────────────────────────────────────────┘
                  │
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                    _bbox_crop_useful()                            │
       │                                                                   │
       │  • Per-category asymmetric bbox padding                           │
       │       (top.bottom = -1.5 %, bottom.bottom = -2.5 %, …)            │
       │  • Per-category percentage short-edge floor                       │
       │       (drop slivers that are < pct% of the source short edge)    │
       │  • Slice the SegFormer mask AND the human mask to the same       │
       │    pixel box — alignment is critical for the next step           │
       └──────────┬───────────────────────────────────────────────────────┘
                  │ list[(det, jpeg_crop, "image/jpeg")]
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                       _matte_crops()                              │
       │                                                                   │
       │  • rembg (u2netp) on each JPEG crop → RGBA alpha cutout          │
       │  • apply_alpha_intersection(rembg_alpha ∩ segformer_mask)         │
       │       with per-category dilation budget (top=1.5 %, foot=2.5 %)  │
       │  • Subtract human-skin from the soft mask post-dilation          │
       │  • Phantom guard: drop matte if solid-alpha < 5 % of canvas      │
       └──────────┬───────────────────────────────────────────────────────┘
                  │ list[(det, png_matte, "image/png")]
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │             _analyse_crops() — batched Gemini VLM                 │
       │                                                                   │
       │  • One multi-modal Gemini-2.5-Flash call carrying ALL N crops    │
       │       (Patch M18 — bypasses Emergent LLM-key concurrency-1)      │
       │  • SegFormer kind hints embedded in the system prompt            │
       │       (Patch M21 — Gemini steered toward the anchored category)  │
       │  • _enforce_segformer_category() post-validates each result      │
       │       (overrides Gemini if it strays outside the anchored set)   │
       │  • Streaming variant — analyze_batch_stream — yields each crop   │
       │    as Gemini emits it (Patch M19, NDJSON to the frontend)        │
       └──────────┬───────────────────────────────────────────────────────┘
                  │ list[analysis dict]
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │                     _fit_crop_to_card()                           │
       │                                                                   │
       │  • Scale-to-fit on a 900x1200 (3:4 portrait) canvas               │
       │       — preserves aspect, never clips                             │
       │  • Always scales the longest side to the canvas edge              │
       │       — small accessories no longer render as tiny dots           │
       │  • RGBA → transparent canvas → PNG output                         │
       │  • RGB  → white canvas       → JPEG output                        │
       │  • Soft-fail on any decode error (returns input bytes unchanged)  │
       └──────────┬───────────────────────────────────────────────────────┘
                  │ list[item dict with crop_base64 + crop_mime + analysis]
                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │            /api/v1/closet/analyze response payload                │
       │                                                                   │
       │  • streaming NDJSON: {detect, count, items_meta} → {item} × N    │
       │       → {done}                                                    │
       │  • or one-shot JSON (axios path, with M17 keepalive whitespace)   │
       └──────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage-by-stage detail

### 3.1 Detection — `clothing_parser.parse_garments`

* **Model:** `sayeed99/segformer_b3_clothes` (transformers, CPU). 18 fashion classes (Upper-clothes, Skirt, Pants, Dress, Footwear, Hat, …).
* **Why SegFormer:** Open-weights, no API spend, 18-class taxonomy that maps cleanly to DressApp categories. Mask-level output is essential for the rembg ∩ SegFormer intersection downstream.
* **Output:** `[{label, kind, bbox_norm[0..1000], mask (HxW bool), confidence}]`.

#### Hardening layered on top of raw SegFormer

| Concern | Implementation |
|---|---|
| Human pixels leak into garment crops | `_extract_human_mask()` builds a Face/Hair/Skin mask from SegFormer's own person classes, dilates it, and **subtracts it from every garment mask** after the dilation step in `apply_alpha_intersection`. |
| Face still survives behind a low-cut top | Geometric head-exclusion: estimate the shoulder line and force the band above it to alpha=0 for tops / outerwear / dresses. |
| Two garments of the same SegFormer class (e.g. layered tops) end up in one bbox | Connected-component split via `_split_same_class_collisions()` — emits one detection per spatial group. |
| One garment splits across two disconnected components (bag body + strap) | `_bridge_mask_components()` — morphological closing then convex-hull bridging, with class-specific kernel sizes. |

### 3.2 Useful-detection filter — `_filter_useful_detections`

* Drops near-full-frame detections (≥90 % of canvas) — those are the "the whole photo is the garment" case and short-circuit to `_handle_already_cropped`.
* Applies **category-aware ordering** before the cap so the first item in each kind always survives (Patch fixed the 6-item-cap-eats-all-shoes bug).
* Cap is configurable (`max_items`, default 10).

### 3.3 Bbox crop — `_crop_to_bbox` + `_bbox_crop_useful`

* **Per-category asymmetric padding** (`_BBOX_PAD_TRBL_BY_CATEGORY`): each edge has its own padding budget. Boundary edges (waistline, ankle) use negative padding (the crop bites INSIDE the SegFormer bbox) to compensate for SegFormer's natural over-claim. Free edges (collar, hat brim, shoe heel) keep generous positive padding so puffy cuffs / brims don't get clipped. See `plan.md` Patches 12j / 12k / 12l.
* **Per-category percentage short-edge floor** (`_resolve_min_short_edge_pct_for_category`): drops slivers below a category-specific fraction of the source short edge. Accessories survive at 8 %; tops require 18 %. Pure-percent (resolution-invariant) — replaces the old absolute-pixel floor that was dropping legitimate shoes on 4 K uploads.
* **Mask alignment invariant:** the SegFormer mask is sliced from the **exact** rectangle the JPEG was cut at (`box_px`), not from a re-computed bbox. Slicing from a separately-computed `bbox_to_pixels(...)` left the mask shifted by up to ~5 % of crop dimensions, corrupting every downstream alpha intersection.

### 3.4 Matting — `_matte_crops`

* **rembg** (`u2netp` ONNX) gives a clean alpha cutout. Serialised — concurrent rembg calls have been observed silently OOM-killing the onnxruntime session on the 3 GB preview pod.
* **`apply_alpha_intersection`** (in `clothing_parser.py`) blends rembg's alpha with the SegFormer per-class mask. Per-category dilation budget (`_DILATE_PCT_BY_CATEGORY`) keeps tight torso garments (top, bottom, dress) at 1.5–1.8 % while letting low-contrast accessories (footwear, hats) keep the original 2.5 % budget.
* **Human-mask subtraction** runs *post*-dilation on the soft mask so rembg's person-shaped foreground can't leak skin / hair back in.
* **Phantom guard** — measure solid-alpha coverage (alpha ≥ 128) of the final RGBA. Below 5 % → drop the detection entirely. Empirically, that's the band where rembg failed on a tiny crop or SegFormer hallucinated. The card the user *would* have seen would have been a blank white tile, so we omit it instead.

### 3.5 VLM analysis — Gemini 2.5 Flash, batched + streamed

* **Why Gemini:** Best vision-language reasoner in the Emergent LLM key. Native multi-modal, no image-encoding boilerplate, structured-output via `response_format=json`.
* **Why batched** (Patch M18): Emergent LLM-key tier serialises concurrent calls to ~1 in flight. 4 sequential 16 s calls = 64 s wall → ingress 502. One batched call with 4 images = ~17 s, same vision work, paid network/prompt overhead once. **3-4× speed-up** on multi-item outfits.
* **Why streamed** (Patch M19): even after batching, the user stares at a blank screen for 17 s. The streaming variant uses `litellm.acompletion(stream=True)`, accumulates text deltas, runs a brace-counting JSON-array scanner after every chunk, and yields each complete `{...}` object as soon as Gemini emits it. The frontend renders N placeholder cards within ~7.5 s and fills them in as they arrive.
* **Category enforcement** (Patch M21): two layers prevent the "coat tail leaks into pants crop → Gemini calls it an Overcoat" failure mode:
  1. **Prompt hint** — every batched call embeds a `CROP CATEGORY HINTS` block ("Image 1: pre-classified as Bottom. Image 2: pre-classified as Top or Outerwear. …").
  2. **Post-validation override** — `_enforce_segformer_category()` runs after `_coerce_enums` and overwrites Gemini's `category` if it strays outside the SegFormer-anchored set. Stamps `_category_overridden_by="segformer"` for triage.

### 3.6 Output normalisation — `_fit_crop_to_card`

The closet card window is `aspect-[3/4]` (portrait). Raw crop bytes coming out of `_matte_crops` span a wide range of aspect ratios — a 4 K source photo with a 25×120 px shoe matte sits next to a 2000×3000 px dress matte, and `object-cover` on the frontend either clips the dress or shrinks the shoe to a sliver. The helper:

1. Decodes the crop (PIL).
2. Computes `scale = min(canvas_w / iw, canvas_h / ih)` — **no upper cap**, so small crops upscale to fill the card and big crops downscale to fit.
3. Resizes with LANCZOS.
4. Composes onto a 900×1200 canvas (transparent for RGBA, white for RGB).
5. Re-encodes — PNG for RGBA, JPEG quality 90 for RGB.
6. Falls back to the original bytes + mime on any decode/encode failure.

Applied at **every** point that emits `crop_base64` to the frontend so Camera, Single-photo, and Batch upload paths all benefit:

* `_build_fullframe_item` — already-cropped product photos
* `_analyse_one_crop` — per-crop fallback path
* `_build_batched_results` — batched (M18) result materialisation
* `analyze_outfit_stream` — streaming `items_meta` placeholder cards
* `analyze_outfit_one_pass` — legacy single-call path

---

## 4. Performance envelope (post-M19)

| Items | Cold start (warmup OK) | Time-to-first-placeholder | Time-to-last-card | Notes |
|---|---|---|---|---|
| 1 | 6–8 s | n/a (single card) | 6–8 s | dominated by Gemini latency |
| 2 | 11–14 s | ~7 s | 11–14 s | batched Gemini wins |
| 4 | 17–22 s | ~7.5 s | 21 s | structural 3× speed-up over per-crop |
| 7+ | scales linearly in detect / matte, flat in Gemini | ~10 s | ~30 s | rembg matting is the bottleneck above 5 items |

Kubernetes ingress 60 s ceiling is **structurally impossible to hit** (Patch M17 keepalive + M19 NDJSON keep the connection active every ~1 s).

---

## 5. Configuration surface

All knobs live in `backend/app/config.py` (env-overrideable):

| Flag | Default | What it does |
|---|---|---|
| `AUTO_MATTE_CROPS` | `true` | Run rembg on the per-crop pipeline. Kill-switch for triage. |
| `DEFER_REMBG_ON_ANALYZE` | `true` | Move rembg matting to a post-save BackgroundTask. `/analyze` returns the bbox JPEG and a deferred-matte marker. |
| `DEFER_RECONSTRUCTION_ON_ANALYZE` | `true` | Move Nano Banana reconstruction to a post-save BackgroundTask. |
| `ENABLE_RECONSTRUCTION` | `false` | Master kill-switch for the auto-reconstruction path (Patch M16). User-driven "Repair photo" CTA is unaffected. |
| `ANALYZE_CONCURRENCY` | `3` | Process-wide `/analyze` semaphore (Patch M15). |
| `ANALYZE_KEEPALIVE_INTERVAL_S` | `8` | Whitespace-keepalive cadence on the non-streaming `/analyze` path. |
| `WARMUP_MODELS_ON_STARTUP` | `true` | Eagerly load SegFormer + rembg + FashionCLIP on FastAPI startup. |
| `BACKGROUND_MATTING_REMBG_MODEL` | `u2netp` | rembg model. `u2netp` is the small/fast one; `birefnet-portrait` is the heavier alternative. |
| `BACKGROUND_MATTING_MAX_EDGE` | `1024` | Resize input to rembg below this many px on the long edge. Alpha is up-sampled back to the original resolution after inference. |

---

## 6. Failure modes (what can go wrong, what catches it)

| Failure | First line of defence | Last line of defence |
|---|---|---|
| SegFormer misses a small accessory | Per-category percentage short-edge floor (low threshold for accessory) | Gemini analyses what SegFormer DID detect; manual Add-Item upload remains available |
| Phantom (empty cutout) lands on the closet | rembg → SegFormer ∩ alpha → 5 % solid-alpha floor | None — empty cards are silently dropped |
| Two layered tops in one bbox | `_split_same_class_collisions` (connected components) | If still merged, Gemini sees one crop and returns one item — user adds the second manually |
| Face leaks under a low-cut top | Human-mask subtraction post-dilation | Geometric head-exclusion (force alpha=0 above the shoulder line for tops/outerwear/dresses) |
| Coat tails leak into pants crop, Gemini calls it "Overcoat" | Negative-padding bbox bite (Patch 12k) | `_enforce_segformer_category` post-validation overrides the category |
| Bag body and strap arrive as two detections | `_bridge_mask_components` morphological closing | Both detections survive; user merges manually in the closet |
| 6+ items detected, cap drops legitimate accessories | Category-aware ordering before cap | None — the cap is a soft limit, easily raised |
| Tiny shoe matte renders as a dot in the card | `_fit_crop_to_card` scale-to-fit on 900×1200 canvas | Frontend `object-cover` is a no-op (crop already matches card aspect) |
| Gemini hallucinates a sub_category for a SegFormer-anchored item | Override clears `sub_category` along with `category` | None — stamped `_category_overridden_by="segformer"` for triage |
| Emergent LLM key throttles concurrent calls | Batched single Gemini call (M18) | Per-crop fallback loop on any batch-level failure |
| Kubernetes ingress 60 s idle ceiling | Streaming NDJSON every ~1 s (M19) | Whitespace keepalive every 8 s on non-streaming path (M17) |
| Cold-start latency on first user upload | `warmup_models()` fires on FastAPI startup (M13) | rembg + reconstruction deferred to BackgroundTask (M14) |

---

## 7. Role in the DressApp ecosystem

GarmentVision is the **only path** into the closet. Every closet item — whether it came from the camera, a single-file upload, a batch upload, or the Chrome extension — passes through `/api/v1/closet/analyze` → `GarmentVisionService.analyze_outfit_stream` → MongoDB.

Downstream:

* **Stylist (`gemini_stylist.py`)** reads `closet_item.analysis` and reasons about colors, dress codes, silhouettes. The richer the analysis, the better the suggestions — so any field GarmentVision drops becomes a Stylist blind spot.
* **Marketplace (`listings.py`)** auto-fills the listing form from `closet_item.analysis` (title, color, condition, category). User can edit, but the defaults set the prior.
* **Outfit reconstruction (`reconstruction.py` + Nano Banana)** uses the original bbox crop and the analysis JSON as the conditioning input. A leaky crop = a leaky reconstruction.
* **Closet search** (Atlas Vector Search) embeds `analysis.description` + `analysis.tags` into FashionCLIP space. Bad fields → bad retrieval.
* **Chrome extension** (`/api/v1/extension/analyze`) calls the same pipeline so a product photo on Zalando/Mango/ASOS is processed identically to a user upload.

In short: **GarmentVision is the schema of DressApp's wardrobe data.** If a field exists on the closet item, GarmentVision is what put it there. That is the role.

---

## 8. Where to look in code

| Concern | File | Symbol |
|---|---|---|
| Top-level orchestration | `garment_vision.py` | `GarmentVisionService.analyze_outfit_stream` |
| One-shot (non-streaming) variant | `garment_vision.py` | `GarmentVisionService.analyze_outfit` |
| SegFormer + human mask | `clothing_parser.py` | `parse_garments`, `_extract_human_mask` |
| Same-class spatial split | `clothing_parser.py` | `_split_same_class_collisions` |
| Mask-fragment bridging | `clothing_parser.py` | `_bridge_mask_components` |
| Alpha intersection + dilation | `clothing_parser.py` | `apply_alpha_intersection`, `_DILATE_PCT_BY_CATEGORY` |
| Bbox cropping | `garment_vision.py` | `_crop_to_bbox`, `_BBOX_PAD_TRBL_BY_CATEGORY` |
| Per-category short-edge floor | `garment_vision.py` | `_resolve_min_short_edge_pct_for_category` |
| rembg wrapper | `background_matting.py` | `matte_crop`, `_rembg_remove` |
| Batched Gemini | `garment_vision.py` | `analyze_batch`, `analyze_batch_stream` |
| Category enforcement | `garment_vision.py` | `_enforce_segformer_category` |
| Canvas normalisation | `garment_vision.py` | `_fit_crop_to_card`, `_CARD_CANVAS_W/H` |
| HTTP endpoint | `api/v1/closet.py` | `analyze_item_image` |
| Frontend stream consumer | `frontend/src/lib/api.js` | `analyzeItemImage` |
| Frontend card UI | `frontend/src/pages/AddItem.jsx` | `ItemCard`, `analyzeCard` |
