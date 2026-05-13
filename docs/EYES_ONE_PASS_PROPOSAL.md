# Eyes single-pass architecture — proposal

> **Goal:** Retire SegFormer + rembg-as-precondition + reconstruction
> revalidation. Replace the entire AddItem analysis pipeline with **one
> call** to the self-hosted Gemma 4 E2B Eyes container.
>
> **Status:** Proposal. No code changes yet. Awaiting user sign-off.

## Why we need this

The current `garment_vision.analyze_outfit(image)` pipeline does, for a
single user upload:

```
detect (SegFormer, ~1-2 s, local)
  │
  ▼
filter + cap detections
  │
  ▼
crop each bbox (PIL, instant)
  │
  ▼
matte each crop with rembg (~10-17 s per crop, serial)
  │
  ▼
analyse each crop with Eyes in parallel (~5-15 s per call, parallel)
  │
  ▼  (if `should_reconstruct(...)` triggers, ~30% of crops)
generate clean studio shot via Nano Banana (~5-10 s)
  │
  ▼
RE-ANALYSE the regenerated image with Eyes (~5-15 s)    ◄── 2nd Eyes call
  │
  ▼
return [{label, bbox, crop_b64, analysis, reconstruction}, ...]
```

For a typical 3-item outfit: **~50-80 s wall-clock** on a healthy
Hetzner box, ~85 s on the preview pod when matting is the bottleneck.

### The architectural problem

- **Gemma 4 E2B is multimodal and intelligent.** It can read a full
  outfit photo and describe every garment in one shot — it does NOT
  need SegFormer to find garments for it.
- **SegFormer is doing only one job we can't easily replace:** giving
  us **pixel-precise per-garment crops** for the closet thumbnails and
  the "share this piece" cards.
- **rembg is doing only one job:** removing background from those
  crops so the thumbnails sit cleanly on the closet grid.
- **Reconstruction's revalidation Eyes call is pure paranoia** — we
  ask Eyes to re-analyse the Nano-Banana-generated image to check the
  category hasn't drifted. It's rejected <5% of the time and costs us
  one extra ~10 s Eyes call on 30% of all crops.

If Eyes can also emit **bounding boxes** alongside the attribute JSON,
we can:
1. Skip SegFormer entirely → save 1-2 s and ~180 MB of in-process RAM.
2. Defer rembg to a *user-initiated* "clean up this photo" action (or
   run it once, async, on the saved crop after the user accepts the
   item) → save 10-17 s × N from the hot path.
3. Make reconstruction opt-in → save one Eyes call on 30% of crops.

Net target latency for a 3-item outfit upload: **~10-15 s** (one Eyes
call returns an array of garments with bboxes; the frontend uses the
original photo + bboxes to render preview cards immediately; rembg
runs in the background per item).

## Proposed schema change

### Current `_GARMENT_OBJECT_SCHEMA` (garment_vision.py:373)

```jsonc
{
  "type": "object",
  "required": ["title"],
  "properties": {
    "name", "title", "caption",
    "category", "sub_category", "item_type",
    "brand", "gender", "dress_code", "season", "tradition",
    "colors[]", "fabric_materials[]", "pattern",
    "state", "condition", "quality",
    "size", "price_cents", "repair_advice", "tags[]"
  }
}
```

No spatial info.

### New schema (proposed)

```jsonc
{
  "type": "object",
  "required": ["title", "region"],
  "properties": {
    // ── NEW: per-garment region on the 0..1000 normalised grid ──
    "region": {
      "type": "object",
      "required": ["bbox"],
      "properties": {
        "bbox": {
          "type": "array",
          "items": { "type": "integer", "minimum": 0, "maximum": 1000 },
          "minItems": 4, "maxItems": 4,
          "description": "[ymin, xmin, ymax, xmax] in 0..1000 normalised coords."
        },
        "confidence": {
          "type": "number", "minimum": 0, "maximum": 1,
          "description": "Eyes' self-reported confidence in the bbox."
        },
        "is_full_frame": {
          "type": "boolean",
          "description": "True when the photo is already a clean single-garment shot (bbox is just [0,0,1000,1000])."
        }
      }
    },
    // ── existing attribute fields, unchanged ──
    "name": ..., "title": ..., "caption": ...,
    "category": ..., "sub_category": ..., "item_type": ...,
    "brand": ..., "gender": ..., "dress_code": ..., "season": ...,
    "tradition": ..., "colors": [...], "fabric_materials": [...],
    "pattern": ..., "state": ..., "condition": ..., "quality": ...,
    "size": ..., "price_cents": ..., "repair_advice": ..., "tags": [...]
  }
}
```

The top-level wrapper keeps the existing `oneOf: object | array of objects`
so single-garment photos return one object and outfit photos return an
array. **Required fields** become `["title", "region"]` so the model
cannot return a garment without telling us where it is in the frame.

## Proposed code changes (high-level, no code yet)

### Backend

1. **Update `EYES_JSON_SCHEMA`** in `garment_vision.py:459` to include
   the `region` field above.

2. **Update `SYSTEM_PROMPT`** (garment_vision.py:300) — add a paragraph
   teaching Eyes:
   > "For each visible garment, include a `region.bbox` array of four
   > integers `[ymin, xmin, ymax, xmax]` on a 0..1000 grid. The bbox
   > should tightly enclose the garment. If the photo is a clean
   > single-garment shot with no clutter, set `region.is_full_frame =
   > true` and use `[0, 0, 1000, 1000]`."

3. **Rewrite `analyze_outfit(image)`** to be a thin wrapper over a
   single `analyze(image)` call that already returns an array:

   ```python
   async def analyze_outfit(image_bytes, *, language=None, think=False):
       parsed = await self.analyze(image_bytes, language=language, think=think)
       garments = parsed if isinstance(parsed, list) else [parsed]
       items = []
       for g in garments:
           region = g.get("region") or {"bbox": [0,0,1000,1000], "is_full_frame": True}
           crop_bytes = _crop_to_bbox(image_bytes, region["bbox"])[0]
           items.append({
               "label": g.get("item_type") or g.get("sub_category") or "garment",
               "kind": _kind_from_category(g.get("category")),
               "bbox": region["bbox"],
               "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
               "crop_mime": "image/jpeg",
               "analysis": _safe_analysis(g),
               # rembg + reconstruction now happen LATER, not on the hot path
           })
       return items
   ```

4. **Move rembg to a background task** triggered from the closet
   `/save` endpoint (not `/analyze`). The frontend gets bbox-cropped
   JPEGs immediately, and the cleaner PNG cutouts arrive seconds later
   when the user is already on the next screen.

5. **Make `should_reconstruct(...)` opt-in.** Frontend exposes a
   "Repair photo" button on the item card; clicking it triggers
   `POST /api/v1/closet/{id}/reconstruct`. Default `state.condition`
   detection still happens in the original Eyes call.

6. **Drop `_ANALYZE_LOCK = Semaphore(1)`.** With rembg out of the hot
   path the memory-pressure justification disappears. Two parallel
   analyzes on a CPX32 (7.6 GB RAM) are safe.

7. **Drop `_detect_via_gemini` and `_detect_via_clothing_parser` from
   the hot path.** Keep them in the file as dead code for one release
   so we have a quick rollback path; delete in the release after.

### Frontend

8. **`AddItemReview` cards render bbox crops immediately**, then
   swap in the rembg PNG when it arrives (frontend polls
   `/closet/{id}` or listens on a WebSocket — TBD).

9. **Add a "Repair photo" CTA** on each item card that triggers the
   opt-in reconstruction flow.

### LoRA / training (the real prerequisite)

The Gemma 4 E2B LoRA was trained to emit the existing 18-field schema.
The new `region` field needs training data.

**Two options, ranked by user cost:**

- **Option α — Prompt-only.** Add the new schema and prompt and try
  zero-shot. Gemma 4 E2B is a strong base model and is likely to
  produce *roughly correct* bboxes from prompt alone, especially when
  constrained by `response_format=json_schema` (llama-server's grammar
  decoder will reject any output that doesn't satisfy the schema). If
  bboxes are within ±10% of ground truth on a 50-image hand-labeled
  set, ship it.

- **Option β — Fine-tune.** Re-run the Colab notebook
  (`docs/Eyes_v2_Merge_Quantize.ipynb`) with the existing dataset
  *plus* bboxes derived from SegFormer outputs as training labels —
  i.e. use SegFormer one last time to bootstrap the new label set,
  then SegFormer is gone forever from the runtime path. ~1-2 h of
  Colab GPU time.

I recommend **starting with α**, measuring bbox accuracy on 50
hand-labeled outfit photos, and only doing β if α misses by more than
±10%.

## What we KEEP (deliberately)

| Component | Why we keep it |
|---|---|
| Gemini 2.5 Flash fallback | Belt-and-suspenders for when Eyes container is down. Triggered only when `_call_gemma_space()` raises. |
| Nano Banana for opt-in reconstruction | "Generate a clean studio shot of this exact garment" is the *purpose-built* use case for an image-generation model. Eyes is not. |
| Local SegFormer model in the repo | One last use: bootstrap training labels for Option β. Once that's done, delete the dependency entirely. |
| rembg | Still useful for the saved closet thumbnail, just not on the hot path. |

## Migration steps (suggested order)

1. **Schema + prompt change**, behind a feature flag
   `EYES_ONE_PASS=false` (default). Old multi-call path stays default.
2. **Hand-label 50 outfit photos** (user does this in Colab/sheet).
3. **Run preview benchmark**: same 50 photos, with `EYES_ONE_PASS=true`
   vs default. Compare:
   - bbox IoU (one-pass vs SegFormer ground truth)
   - attribute field-by-field diff
   - latency p50 / p95
4. If bbox IoU ≥ 0.7 on 90%+ of photos → flip the flag default to `true`
   in `deploy/.env.example` (production), keep `false` in preview
   (preview can't run Eyes anyway).
5. After two weeks of stable production traffic → delete the SegFormer
   + rembg-on-hot-path code paths. Move SegFormer to a one-shot script
   `scripts/label_outfits_for_training.py` for any future LoRA refresh.

## Estimated impact

| Metric | Before | After (target) |
|---|---|---|
| Single-item AddItem (Hetzner) | 25-40 s | 8-12 s |
| 3-item outfit AddItem (Hetzner) | 50-80 s | 12-18 s |
| RAM during analysis | ~3.5 GB (SegFormer + rembg + Eyes container) | ~2.8 GB (Eyes container only) |
| Eyes calls per crop | 1-2 (with reconstruction revalidation) | 1 |
| Reconstruction credits spent | every triggered crop, blocking | only when user opts in, background |

## Open questions for the user

1. **Option α or β** for the bbox training? (Defaults to α.)
2. **Reconstruction CTA placement** — on every item card, or only when
   `should_reconstruct()` heuristic says it's worth offering?
3. **rembg background timing** — kick off on `/analyze` (so the
   cutout is ready before the user clicks save) or only on `/save`
   (cheaper, but the cutout shows up a few seconds late)?
4. **Can the user share 20-50 hand-cropped outfit photos with bbox
   ground truth** so we have a benchmark set, or should I write a
   small Colab notebook that uses SegFormer to auto-label some?
5. **Acceptance criteria** — what bbox IoU threshold counts as "good
   enough to ship"? I suggest 0.7 for 90% of photos.

No code will be written until these are answered.
