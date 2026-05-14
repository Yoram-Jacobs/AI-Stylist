#!/usr/bin/env python3
"""
Generator for ``docs/notebooks/Eyes_OnePass_Benchmark.ipynb``.

This script builds the notebook from clean Python source strings rather
than hand-crafting JSON, so the cells stay readable in code review and
the .ipynb file can be regenerated reproducibly when the bench protocol
changes.

Run from anywhere::

    python3 /app/scripts/build_eyes_benchmark_notebook.py

Output:
    /app/docs/notebooks/Eyes_OnePass_Benchmark.ipynb
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/app/docs/notebooks/Eyes_OnePass_Benchmark.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────
# Cell sources (raw strings — newlines preserved exactly).
# ──────────────────────────────────────────────────────────────────────

MD_TITLE = """\
# Eyes One-Pass — Bounding-Box Benchmark (Phase O.6, Option α)

> **Purpose:** Quantify how well the single-pass Eyes pipeline
> (``EYES_ONE_PASS=true``) localises garments **without retraining the
> LoRA** — i.e. relying only on the new system-prompt suffix and
> ``response_format=json_schema`` grammar constraint.
>
> **Gate to flip the flag default to `true` in production:**
> `bbox IoU ≥ 0.7 on 90 % of photos`. See
> [`/app/docs/EYES_ONE_PASS_PROPOSAL.md`](../EYES_ONE_PASS_PROPOSAL.md).

## Inputs

| Asset | Path | Provided by |
| --- | --- | --- |
| Outfit photos | `/data/ccp-DatasetNinja/ds/img/` | CCP DatasetNinja (uploaded May-2026) |
| Ground-truth masks | `/data/ccp-DatasetNinja/ds/ann/` | CCP DatasetNinja (Supervisely bitmap format) |
| Eyes API | `${API_URL}/api/v1/closet/analyze` | Production Hetzner deploy (or any backend with `EYES_ONE_PASS=true`) |
| Auth token | `${EYES_BENCH_TOKEN}` env var | A user account on the target backend |

## Outputs

* `/app/data/benchmark_labels.json` — human-verified GT bboxes (one row per photo).
* `/app/data/benchmark_predictions.json` — per-photo `/analyze` responses, cached so re-runs are cheap.
* `/app/data/benchmark_results.csv` — IoU + class match per (photo, GT garment).
* Printed verdict in the final cell: **PASS** (flip the flag) or **FAIL** (iterate prompt → Option β).

## How to run

1. Set the two env vars at the top of cell 2.
2. **Run all cells top to bottom.** Cells 4-5 are the verification UI: accept/reject the auto-derived bboxes. The rest is mechanical.
3. The final cell prints the gate decision and a one-shot diff for `deploy/.env.example` if the gate passes.
"""

CELL_SETUP = """\
# ── Cell 2 — Setup, deps, config ──────────────────────────────────────
import os, sys, json, base64, io, zlib, time, re
from pathlib import Path
from collections import defaultdict

# Install the (small) extras this notebook needs. Safe to re-run.
# When you run this from Colab uncomment the pip line; locally the
# packages are already in the backend venv.
# !pip install -q ipywidgets httpx Pillow numpy pandas

import httpx
import numpy as np
import pandas as pd
from PIL import Image
import ipywidgets as W
from IPython.display import display, clear_output

# ── User-configurable parameters ──────────────────────────────────────
API_URL = os.environ.get(
    "EYES_BENCH_API_URL",
    "https://ai-stylist-api.preview.emergentagent.com",   # change for prod
)
TOKEN = os.environ.get("EYES_BENCH_TOKEN", "")
NUM_PHOTOS = int(os.environ.get("EYES_BENCH_PHOTOS", "30"))
DATASET_ROOT = Path(os.environ.get(
    "EYES_BENCH_DATASET", "/data/ccp-DatasetNinja/ds",
))
OUT_DIR = Path(os.environ.get(
    "EYES_BENCH_OUT", "/app/data",
)).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)

# CCP / Supervisely classes that are NOT garments — excluded from GT.
NON_GARMENT = {"skin", "hair", "null", "background", "face"}

# Eyes' bbox grid (0..1000 normalised, [ymin,xmin,ymax,xmax]).
GRID = 1000

print(f"API_URL       = {API_URL}")
print(f"TOKEN length  = {len(TOKEN)} chars ({'set' if TOKEN else 'MISSING — set EYES_BENCH_TOKEN'})")
print(f"NUM_PHOTOS    = {NUM_PHOTOS}")
print(f"DATASET_ROOT  = {DATASET_ROOT} (exists={DATASET_ROOT.is_dir()})")
print(f"OUT_DIR       = {OUT_DIR}")
"""

CELL_BITMAP_TO_BBOX = '''\
# ── Cell 3 — Convert CCP bitmap annotations to bboxes ─────────────────
#
# CCP/Supervisely encodes per-garment masks as base64(zlib(PNG bytes))
# stored under ``objects[i].bitmap.data`` with an ``origin: [x, y]``
# offset pointing to the mask's top-left in the original image. We
# decode the PNG, find the mask's tight bounding box in mask-local
# coords, add the origin back, and normalise to the 0..1000 grid Eyes
# uses. Returns one row per (image, garment) pair.

def _mask_bbox_local(png_bytes: bytes) -> tuple[int, int, int, int] | None:
    """Tight bbox of the non-zero region of a Supervisely mask PNG."""
    img = Image.open(io.BytesIO(png_bytes)).convert("L")
    arr = np.asarray(img)
    ys, xs = np.where(arr > 0)
    if ys.size == 0:
        return None
    return int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1


def derive_gt_bboxes(ann_path: Path) -> dict:
    """Open one CCP annotation JSON, return ``{size, garments: [..]}``.

    Each garment row has::

        {
          "class":   "jacket" | "pants" | ...,
          "bbox_px": [ymin, xmin, ymax, xmax]      # original pixel coords
          "bbox_n":  [ymin, xmin, ymax, xmax]      # normalised 0..1000
        }
    """
    d = json.loads(ann_path.read_text())
    H, W = d["size"]["height"], d["size"]["width"]
    out = []
    for obj in d.get("objects", []):
        cls = (obj.get("classTitle") or "").lower()
        if cls in NON_GARMENT:
            continue
        if obj.get("geometryType") != "bitmap":
            continue
        bm = obj.get("bitmap") or {}
        origin = bm.get("origin")
        data = bm.get("data")
        if not (origin and data):
            continue
        try:
            raw = zlib.decompress(base64.b64decode(data))
        except Exception:
            continue
        local = _mask_bbox_local(raw)
        if not local:
            continue
        ly0, lx0, ly1, lx1 = local
        ox, oy = origin
        y0, x0, y1, x1 = oy + ly0, ox + lx0, oy + ly1, ox + lx1
        # Clamp to image bounds (some masks bleed by ±1 pixel).
        y0, y1 = max(0, y0), min(H, y1)
        x0, x1 = max(0, x0), min(W, x1)
        if y1 <= y0 or x1 <= x0:
            continue
        n = [int(y0 / H * GRID), int(x0 / W * GRID),
             int(y1 / H * GRID), int(x1 / W * GRID)]
        out.append({"class": cls,
                    "bbox_px": [y0, x0, y1, x1],
                    "bbox_n":  n})
    return {"size": [H, W], "garments": out}


# Sample N photos and build the auto-derived label table.
img_dir = DATASET_ROOT / "img"
ann_dir = DATASET_ROOT / "ann"
all_imgs = sorted(p.name for p in img_dir.glob("*.jpg"))
sampled = all_imgs[:NUM_PHOTOS]

auto_labels: dict[str, dict] = {}
for fname in sampled:
    ann_path = ann_dir / f"{fname}.json"
    if not ann_path.exists():
        print(f"  WARN: missing annotation for {fname}, skipping")
        continue
    auto_labels[fname] = derive_gt_bboxes(ann_path)

print(f"Derived auto-labels for {len(auto_labels)} photos")
print(f"Total garment bboxes:   {sum(len(p['garments']) for p in auto_labels.values())}")
print()
print("Per-class counts:")
class_counts: dict[str, int] = defaultdict(int)
for p in auto_labels.values():
    for g in p["garments"]:
        class_counts[g["class"]] += 1
for c, n in sorted(class_counts.items(), key=lambda kv: -kv[1]):
    print(f"  {n:4d}  {c}")
'''

CELL_VERIFY_UI = '''\
# ── Cell 4 — Visual verification UI (accept / reject / edit) ───────────
#
# The CCP masks are very tight; sometimes they exclude a sleeve or
# include the wearer's hand. We render each photo with its auto-derived
# bboxes overlaid and let the user accept/reject each one (or remove
# spurious classes). Edits write to ``verified_labels`` which the IoU
# evaluator below consumes. This UI is single-photo at a time so it's
# usable in a small Jupyter pane.

from PIL import ImageDraw, ImageFont
verified_labels: dict[str, list[dict]] = {}

def _render_with_boxes(img_path: Path, garments: list[dict]) -> Image.Image:
    im = Image.open(img_path).convert("RGB").copy()
    d = ImageDraw.Draw(im, "RGBA")
    for i, g in enumerate(garments):
        y0, x0, y1, x1 = g["bbox_px"]
        d.rectangle([x0, y0, x1, y1], outline=(255, 80, 80, 230), width=3)
        d.text((x0 + 4, y0 + 2), f"{i}: {g['class']}", fill=(255, 240, 240))
    return im


class _ReviewState:
    def __init__(self, names: list[str]):
        self.names = names
        self.idx = 0
    def current(self) -> str | None:
        return self.names[self.idx] if self.idx < len(self.names) else None


state = _ReviewState(list(auto_labels.keys()))

out = W.Output()
img_w = W.Image(format="jpeg", width=400)
info  = W.HTML()
classes_box = W.VBox(layout={"max_height": "240px", "overflow_y": "auto"})
prev_btn  = W.Button(description="← Prev",  layout={"width": "auto"})
next_btn  = W.Button(description="Save & Next →",
                     button_style="success", layout={"width": "auto"})
skip_btn  = W.Button(description="Skip", layout={"width": "auto"})
progress = W.HTML()

def render():
    name = state.current()
    if not name:
        out.clear_output()
        img_w.value = b""
        info.value = "<b>All photos reviewed.</b>"
        classes_box.children = []
        progress.value = ""
        return
    src = auto_labels[name]
    im = _render_with_boxes(img_dir / name, src["garments"])
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=80)
    img_w.value = buf.getvalue()
    info.value = (
        f"<b>{name}</b> &middot; {len(src['garments'])} bboxes &middot; "
        f"image {src['size'][1]}×{src['size'][0]}"
    )
    progress.value = (
        f"<i>Photo {state.idx + 1} / {len(state.names)} &middot; "
        f"verified {len(verified_labels)}</i>"
    )
    cbs = []
    for i, g in enumerate(src["garments"]):
        cb = W.Checkbox(value=True,
                        description=f"[{i}] {g['class']}",
                        indent=False)
        cb._gt_idx = i
        cbs.append(cb)
    classes_box.children = cbs

def on_next(_):
    name = state.current()
    if not name: return
    keep = [auto_labels[name]["garments"][cb._gt_idx]
            for cb in classes_box.children if cb.value]
    verified_labels[name] = keep
    state.idx += 1
    render()

def on_prev(_):
    if state.idx > 0:
        state.idx -= 1
        render()

def on_skip(_):
    state.idx += 1
    render()

next_btn.on_click(on_next)
prev_btn.on_click(on_prev)
skip_btn.on_click(on_skip)

display(W.VBox([
    progress, info,
    W.HBox([img_w, W.VBox([
        W.HTML("<b>Garments to keep</b>"),
        classes_box,
        W.HBox([prev_btn, skip_btn, next_btn]),
    ], layout={"margin": "0 0 0 16px"})]),
]))
render()
'''

CELL_SAVE_LABELS = '''\
# ── Cell 5 — Persist verified labels ──────────────────────────────────
#
# Run this AFTER you've worked through the review UI in cell 4. Writes
# the human-accepted bboxes to ``benchmark_labels.json`` so the IoU
# evaluator below has a stable input.

labels_path = OUT_DIR / "benchmark_labels.json"
labels_path.write_text(json.dumps({
    "schema_version": 1,
    "dataset": "ccp-DatasetNinja",
    "grid": GRID,
    "labels": {k: {"size": auto_labels[k]["size"], "garments": v}
               for k, v in verified_labels.items()},
}, indent=2))
print(f"Wrote {len(verified_labels)} verified photos to {labels_path}")
'''

CELL_CALL_EYES = '''\
# ── Cell 6 — Call /closet/analyze with EYES_ONE_PASS for each photo ───
#
# The backend the target ``API_URL`` points at MUST have
# ``EYES_ONE_PASS=true`` set in its environment. The notebook simply
# POSTs the photo and reads the bbox out of each item in the response.
# Predictions are cached to ``benchmark_predictions.json`` so re-runs of
# the analysis cells below don't re-hit the API.

assert TOKEN, "EYES_BENCH_TOKEN env var must be set"
pred_path = OUT_DIR / "benchmark_predictions.json"
predictions: dict[str, list[dict]] = (
    json.loads(pred_path.read_text()).get("predictions", {})
    if pred_path.exists() else {}
)

H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

async def _analyze_one(client: httpx.AsyncClient, fname: str) -> list[dict]:
    if fname in predictions:
        return predictions[fname]
    raw = (img_dir / fname).read_bytes()
    body = {
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "multi": True,
        "language": "en",
    }
    t0 = time.perf_counter()
    r = await client.post(f"{API_URL}/api/v1/closet/analyze",
                          json=body, headers=H, timeout=120)
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        print(f"  {fname}: HTTP {r.status_code} — {r.text[:200]}")
        return []
    data = r.json()
    items = data.get("items", [])
    print(f"  {fname:20s}  {len(items)} item(s)  {dt:.1f}s  "
          f"one_pass={items[0].get('one_pass') if items else '?'}")
    return items


import asyncio
async def _run():
    async with httpx.AsyncClient() as c:
        for fname in verified_labels.keys():
            preds = await _analyze_one(c, fname)
            predictions[fname] = preds
            # Save after every photo so a Ctrl-C doesn't lose work.
            pred_path.write_text(json.dumps({"predictions": predictions}, indent=2))

await _run()
print()
print(f"Wrote {len(predictions)} predictions to {pred_path}")
'''

CELL_IOU = '''\
# ── Cell 7 — Per-photo IoU + 90th-percentile verdict ──────────────────
#
# Matching protocol
# -----------------
# For each photo we have:
#   • N_gt GT bboxes (from ``verified_labels``)
#   • N_pred predicted bboxes (from ``predictions[fname]``)
#
# We greedily match each prediction to its highest-IoU unclaimed GT
# bbox. Per-photo score = mean IoU over MATCHED pairs (unmatched preds
# and unmatched GTs do NOT pull the average down; this is forgiving of
# "lumping", which Option α inherently does without a re-trained LoRA).
# A photo PASSES if its mean IoU >= 0.7. The gate is: PASS-rate >= 0.9.
#
# To penalise lumping more strictly later, swap to "score = mean over
# all GT bboxes including unmatched (counted as IoU=0)". For Option α
# the lenient version is the right starting point — it tells us "when
# Eyes does emit a bbox, how accurate is it?".

def iou(a: list[int], b: list[int]) -> float:
    y0 = max(a[0], b[0]); x0 = max(a[1], b[1])
    y1 = min(a[2], b[2]); x1 = min(a[3], b[3])
    inter = max(0, y1 - y0) * max(0, x1 - x0)
    if inter == 0: return 0.0
    a_area = (a[2] - a[0]) * (a[3] - a[1])
    b_area = (b[2] - b[0]) * (b[3] - b[1])
    return inter / float(a_area + b_area - inter)


rows = []
photo_scores = []
for fname, gts in verified_labels.items():
    preds = predictions.get(fname, [])
    pred_bboxes = [p.get("bbox") for p in preds if p.get("bbox")]
    claimed = set()
    pairs = []
    for pi, pb in enumerate(pred_bboxes):
        best_iou = 0.0; best_gi = -1
        for gi, g in enumerate(gts):
            if gi in claimed: continue
            v = iou(pb, g["bbox_n"])
            if v > best_iou:
                best_iou = v; best_gi = gi
        if best_gi >= 0 and best_iou > 0:
            claimed.add(best_gi)
            pairs.append((pi, best_gi, best_iou))
            rows.append({
                "photo": fname,
                "pred_idx": pi, "gt_idx": best_gi,
                "gt_class": gts[best_gi]["class"],
                "iou": round(best_iou, 3),
                "pred_bbox": pb,
                "gt_bbox":   gts[best_gi]["bbox_n"],
            })
        else:
            rows.append({
                "photo": fname, "pred_idx": pi, "gt_idx": -1,
                "gt_class": None, "iou": 0.0,
                "pred_bbox": pb, "gt_bbox": None,
            })
    # Photos with zero predictions: score = 0 (Eyes returned nothing).
    if pred_bboxes:
        mean_iou = float(np.mean([p[2] for p in pairs])) if pairs else 0.0
    else:
        mean_iou = 0.0
    photo_scores.append({"photo": fname,
                          "n_pred": len(pred_bboxes),
                          "n_gt": len(gts),
                          "matched": len(pairs),
                          "mean_iou": round(mean_iou, 3),
                          "passes_0_7": mean_iou >= 0.7})

df = pd.DataFrame(rows)
photo_df = pd.DataFrame(photo_scores).sort_values("mean_iou")

results_csv = OUT_DIR / "benchmark_results.csv"
df.to_csv(results_csv, index=False)
print(f"Wrote {len(df)} pair rows to {results_csv}")
print()
print("Per-photo summary (sorted worst → best):")
print(photo_df.to_string(index=False))
'''

CELL_VERDICT = '''\
# ── Cell 8 — Gate decision + one-shot env diff ────────────────────────
pass_rate = (photo_df["passes_0_7"].sum() / len(photo_df)) if len(photo_df) else 0
p50 = photo_df["mean_iou"].median() if len(photo_df) else 0
p90_iou = photo_df["mean_iou"].quantile(0.9) if len(photo_df) else 0
print(f"Photos evaluated : {len(photo_df)}")
print(f"Pass rate (IoU>=0.7) : {pass_rate:.0%}     [gate: >=90%]")
print(f"Median per-photo IoU : {p50:.3f}")
print(f"90th-pct per-photo IoU : {p90_iou:.3f}")
print()
if pass_rate >= 0.9:
    print("VERDICT: PASS — flip the flag in production.")
    print()
    print("    deploy/.env.example diff (apply with sed or by hand):")
    print()
    print("    -EYES_ONE_PASS=false")
    print("    +EYES_ONE_PASS=true")
    print()
    print("    Then on the Hetzner box:")
    print("      docker compose -f deploy/docker-compose.yml restart backend")
    print()
    print("    Verify with:")
    print("      curl -s $API/api/v1/closet/analyze/version | jq")
else:
    miss = 0.9 - pass_rate
    print(f"VERDICT: FAIL — short by {miss:.0%} pass-rate.")
    print()
    if pass_rate >= 0.7:
        print("  Close-but-not-quite. Try one prompt iteration first")
        print("  (extend SYSTEM_PROMPT_ONE_PASS_SUFFIX with more examples")
        print("  of multi-item enumeration, then re-run cells 6-8).")
    else:
        print("  Big miss. Option β (LoRA re-train with SegFormer-bootstrapped")
        print("  bboxes) is now the recommended next step. See")
        print("  /app/docs/EYES_ONE_PASS_PROPOSAL.md \\u00a7\\\"Two options, ranked")
        print("  by user cost\\\" for the procedure.")
'''


def cell_md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {},
            "source": src.splitlines(keepends=True)}


def cell_code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": src.splitlines(keepends=True)}


notebook = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python",
                        "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
        "dressapp": {"phase": "O.6", "doc": "EYES_ONE_PASS_PROPOSAL.md"},
    },
    "cells": [
        cell_md(MD_TITLE),
        cell_code(CELL_SETUP),
        cell_code(CELL_BITMAP_TO_BBOX),
        cell_code(CELL_VERIFY_UI),
        cell_code(CELL_SAVE_LABELS),
        cell_code(CELL_CALL_EYES),
        cell_code(CELL_IOU),
        cell_code(CELL_VERDICT),
    ],
}

OUT.write_text(json.dumps(notebook, indent=1) + "\n")
print(f"Wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(notebook['cells'])} cells)")
