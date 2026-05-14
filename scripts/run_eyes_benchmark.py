"""In-pod Eyes-One-Pass benchmark against the CCP-Ninja dataset.

Reads every annotated image under ``/app/inference-server/eyes/test_images``,
calls ``garment_vision_service.analyze_outfit_one_pass`` directly (bypassing
the ``EYES_ONE_PASS`` env flag so the benchmark is reproducible regardless
of deploy state), pairs each predicted bbox to the best-IoU ground-truth
garment bbox, and prints/writes IoU + precision/recall numbers.

Why this exists
---------------
The Eyes-One-Pass rollout runbook
(``docs/EYES_ONE_PASS_RUNBOOK.md``) makes flipping the flag in production
conditional on a measured bbox-accuracy gate. The original gating plan
ran the benchmark inside Colab, which required exporting a user JWT
into Colab Secrets — an awkward workflow that bit us once already (see
``WASTED_WORK_REPORT.md`` and the May 14 chat thread). This script
replaces the Colab path entirely: the dataset lives in-repo, the
Eyes service lives in-process, the report falls out at the end.

What this measures (and what it doesn't)
----------------------------------------
* In a **preview pod** this benchmarks Gemini-2.5-Flash via the
  ``EYES_PROVIDER=gemini`` path. That's the *fallback* leg.
* To benchmark the **primary** Hetzner Gemma-4 E2B, the same script
  needs to run on the production VPS inside the ``backend`` container
  (so it can reach ``http://eyes:7860``). Same code, different pod.
* 30 images is a smoke-grade gate — sufficient for a go/no-go on the
  flag flip, NOT a publishable accuracy claim. Plan a bigger crawl
  (1-5 k images) before any external announcement.

Gate (matches the runbook ``mean IoU >= 0.6, recall@0.5 >= 0.8``)
-----------------------------------------------------------------
* **mean IoU >= 0.6** across all matched (pred, GT) pairs
* **recall @ IoU=0.5 >= 0.8** — fraction of GT garment bboxes that any
  prediction covers with IoU >= 0.5

If both pass on this 30-image set, we have enough confidence to flip
``EYES_ONE_PASS=true`` in the next deploy and let real-world traffic
expose any tail-case regression.

Outputs
-------
* ``/tmp/eyes_benchmark.json`` — full per-image + per-pair detail
* ``/tmp/eyes_benchmark.md`` — human-readable runbook gate table

Usage
-----
    /root/.venv/bin/python /app/scripts/run_eyes_benchmark.py
    /root/.venv/bin/python /app/scripts/run_eyes_benchmark.py --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import logging
import statistics
import sys
import time
import zlib
from pathlib import Path
from typing import Any

# Make the FastAPI package importable so we can call the service
# without spinning up a real HTTP server.
sys.path.insert(0, "/app/backend")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.services.garment_vision import garment_vision_service  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("eyes_bench")
logger.setLevel(logging.INFO)

DATASET_DIR = Path("/app/inference-server/eyes/test_images")

# CCP class titles that we care about. Skin / hair / null are body parts
# / background, not garments — the analyzer shouldn't be expected to
# return them and including them would deflate recall artificially.
GARMENT_CLASSES = {
    # Tops
    "blouse", "shirt", "sweater", "t-shirt", "tee", "vest", "tank",
    # Bottoms
    "pants", "skirt", "jeans", "leggings", "shorts",
    # Outerwear
    "coat", "jacket", "cape", "blazer",
    # Full-body
    "dress", "romper", "suit",
    # Footwear
    "shoes", "boots", "heels", "pumps", "sandals", "wedges",
    "socks", "stockings",
    # Accessories that take up enough pixel area to register as a bbox
    "bag", "purse", "wallet",
    "belt",
    "necklace", "hat", "sunglasses", "glasses",
    "accessories",
}

# Anything in this set is intentionally ignored when building GT.
EXCLUDED_CLASSES = {"skin", "hair", "null", ""}

IOU_MATCH_THRESHOLD = 0.5


# -----------------------------------------------------------------
# Ground-truth bbox extraction
# -----------------------------------------------------------------
def _mask_bbox(bitmap_obj: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Decode a Supervisely-format bitmap mask -> enclosing pixel bbox.

    Format: ``base64( zlib( PNG_bytes ) )``. The PNG is a single-channel
    mask the size of the masked region, positioned at ``origin=[x, y]``
    inside the full image. Returns ``(x_min, y_min, x_max, y_max)`` in
    *full-image* pixel coordinates, or ``None`` if the mask is empty.
    """
    b = base64.b64decode(bitmap_obj["data"])
    try:
        inner = zlib.decompress(b)
    except zlib.error:
        # Some datasets ship the PNG bytes without an outer zlib layer.
        inner = b
    img = Image.open(io.BytesIO(inner))
    arr = np.array(img)
    if arr.ndim == 3:
        # Some mask exports include an alpha channel — collapse to 1ch.
        arr = arr.max(axis=2)
    ys, xs = np.nonzero(arr)
    if ys.size == 0 or xs.size == 0:
        return None
    ox, oy = bitmap_obj["origin"]
    return (
        int(ox + xs.min()),
        int(oy + ys.min()),
        int(ox + xs.max()),
        int(oy + ys.max()),
    )


def _load_ground_truth(ann_path: Path) -> tuple[tuple[int, int], list[dict[str, Any]]]:
    """Return ``((width, height), [garment_records])`` for one image."""
    doc = json.loads(ann_path.read_text())
    size = doc.get("size") or {}
    w = int(size.get("width") or 0)
    h = int(size.get("height") or 0)
    garments: list[dict[str, Any]] = []
    for obj in doc.get("objects", []):
        cls = (obj.get("classTitle") or "").lower().strip()
        if cls in EXCLUDED_CLASSES or cls not in GARMENT_CLASSES:
            continue
        if obj.get("geometryType") != "bitmap":
            continue
        bbox = _mask_bbox(obj["bitmap"])
        if bbox is None:
            continue
        garments.append({
            "class": cls,
            "bbox": bbox,
            # area is useful as a sort key + for the per-image report
            "area": (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]),
        })
    return (w, h), garments


# -----------------------------------------------------------------
# Prediction bbox extraction
# -----------------------------------------------------------------
def _pred_bbox_to_pixels(
    bbox_norm: list[int] | tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Convert Eyes' [ymin, xmin, ymax, xmax] on a 0..1000 grid into
    full-resolution pixel ``(x_min, y_min, x_max, y_max)``."""
    ymin_n, xmin_n, ymax_n, xmax_n = bbox_norm
    return (
        int(round(xmin_n / 1000.0 * width)),
        int(round(ymin_n / 1000.0 * height)),
        int(round(xmax_n / 1000.0 * width)),
        int(round(ymax_n / 1000.0 * height)),
    )


# -----------------------------------------------------------------
# IoU
# -----------------------------------------------------------------
def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Axis-aligned bbox IoU. Boxes are ``(x_min, y_min, x_max, y_max)``."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0, inter_x2 - inter_x1)
    ih = max(0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    a_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    b_area = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = a_area + b_area - inter
    return float(inter) / float(union) if union > 0 else 0.0


def _match_greedy(
    preds: list[tuple[int, int, int, int]],
    gts: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, float]]:
    """Greedy max-IoU one-to-one matching.

    Returns a list of ``(pred_idx, gt_idx, iou)`` tuples. Each GT and
    each prediction is used at most once. Unmatched predictions /
    GTs are reported separately at the call site.
    """
    matrix: list[tuple[float, int, int]] = []
    for pi, p in enumerate(preds):
        for gi, g in enumerate(gts):
            iou = _iou(p, g)
            if iou > 0:
                matrix.append((iou, pi, gi))
    matrix.sort(key=lambda t: -t[0])
    used_p: set[int] = set()
    used_g: set[int] = set()
    matched: list[tuple[int, int, float]] = []
    for iou, pi, gi in matrix:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)
        matched.append((pi, gi, iou))
    return matched


# -----------------------------------------------------------------
# Per-image benchmark
# -----------------------------------------------------------------
async def _benchmark_one_image(jpg_path: Path) -> dict[str, Any]:
    ann_path = jpg_path.with_suffix(jpg_path.suffix + ".json")
    if not ann_path.exists():
        return {"image": jpg_path.name, "skipped": "no annotation"}

    (gt_w, gt_h), gts = _load_ground_truth(ann_path)
    image_bytes = jpg_path.read_bytes()

    # Use the actual image dimensions (the annotation 'size' field can
    # drift from the real image — read PIL for ground truth).
    with Image.open(io.BytesIO(image_bytes)) as im:
        img_w, img_h = im.size
    # Sanity: annotations might mismatch slightly but should be close.
    if gt_w and gt_h and (abs(gt_w - img_w) > 4 or abs(gt_h - img_h) > 4):
        logger.warning(
            "%s: annotation size %dx%d differs from image %dx%d",
            jpg_path.name, gt_w, gt_h, img_w, img_h,
        )

    t0 = time.perf_counter()
    try:
        result = await garment_vision_service.analyze_outfit_one_pass(
            image_bytes, language="en",
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "image": jpg_path.name,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "n_gt": len(gts),
        }
    elapsed = time.perf_counter() - t0

    preds: list[dict[str, Any]] = []
    for it in result:
        bb = it.get("bbox")
        if not (isinstance(bb, (list, tuple)) and len(bb) == 4):
            continue
        preds.append({
            "label": it.get("label") or "",
            "bbox": _pred_bbox_to_pixels(bb, img_w, img_h),
            "category": ((it.get("analysis") or {}).get("category") or ""),
        })

    matched = _match_greedy(
        [p["bbox"] for p in preds],
        [g["bbox"] for g in gts],
    )
    matched_set_pred = {pi for pi, _, _ in matched}
    matched_set_gt = {gi for _, gi, _ in matched}
    pairs = [
        {
            "pred_label": preds[pi]["label"],
            "pred_cat": preds[pi]["category"],
            "gt_class": gts[gi]["class"],
            "iou": round(iou, 4),
            "passes_match": iou >= IOU_MATCH_THRESHOLD,
        }
        for pi, gi, iou in matched
    ]
    n_pred_matched_05 = sum(1 for p in pairs if p["passes_match"])
    return {
        "image": jpg_path.name,
        "elapsed_s": round(elapsed, 2),
        "img_size": [img_w, img_h],
        "n_gt": len(gts),
        "n_pred": len(preds),
        "n_matched_above_iou_05": n_pred_matched_05,
        "unmatched_preds": [
            {"label": preds[i]["label"], "bbox": preds[i]["bbox"]}
            for i in range(len(preds)) if i not in matched_set_pred
        ],
        "unmatched_gts": [
            {"class": gts[i]["class"], "bbox": gts[i]["bbox"]}
            for i in range(len(gts)) if i not in matched_set_gt
        ],
        "pairs": pairs,
    }


# -----------------------------------------------------------------
# Aggregation
# -----------------------------------------------------------------
def _aggregate(per_image: list[dict[str, Any]]) -> dict[str, Any]:
    """Crunch per-image results into the runbook gate table."""
    all_pairs = [p for r in per_image for p in r.get("pairs", [])]
    ious = [p["iou"] for p in all_pairs]

    n_gt = sum(r.get("n_gt", 0) for r in per_image)
    n_pred = sum(r.get("n_pred", 0) for r in per_image)
    n_match_05 = sum(r.get("n_matched_above_iou_05", 0) for r in per_image)

    def pct(p: float) -> float:
        if not ious:
            return 0.0
        return float(np.percentile(ious, p))

    summary = {
        "n_images": len(per_image),
        "n_images_failed": sum(1 for r in per_image if "error" in r),
        "n_gt_garments_total": n_gt,
        "n_predictions_total": n_pred,
        "n_pairs_matched": len(all_pairs),
        "n_matched_at_iou_0_5": n_match_05,
        "mean_iou": round(statistics.mean(ious), 4) if ious else 0.0,
        "median_iou": round(statistics.median(ious), 4) if ious else 0.0,
        "p25_iou": round(pct(25), 4),
        "p75_iou": round(pct(75), 4),
        "p95_iou": round(pct(95), 4),
        "recall_at_iou_0_5": round(n_match_05 / n_gt, 4) if n_gt else 0.0,
        "precision_at_iou_0_5": round(n_match_05 / n_pred, 4) if n_pred else 0.0,
    }

    # Per-class recall — useful to spot accessories vs full-body bias.
    by_class: dict[str, dict[str, int]] = {}
    for r in per_image:
        for gi, gt_class in enumerate(
            g["class"] for g in (r.get("unmatched_gts", []))
        ):
            by_class.setdefault(gt_class, {"n_gt": 0, "n_matched": 0})
            by_class[gt_class]["n_gt"] += 1
    for r in per_image:
        for p in r.get("pairs", []):
            cls = p["gt_class"]
            by_class.setdefault(cls, {"n_gt": 0, "n_matched": 0})
            by_class[cls]["n_gt"] += 1
            if p["passes_match"]:
                by_class[cls]["n_matched"] += 1
    summary["per_class"] = {
        cls: {
            "n_gt": v["n_gt"],
            "recall_at_0_5": (
                round(v["n_matched"] / v["n_gt"], 4) if v["n_gt"] else 0.0
            ),
        }
        for cls, v in sorted(by_class.items())
    }
    return summary


# -----------------------------------------------------------------
# Markdown report
# -----------------------------------------------------------------
def _render_markdown(summary: dict[str, Any], per_image: list[dict[str, Any]]) -> str:
    gate_mean = summary["mean_iou"] >= 0.6
    gate_recall = summary["recall_at_iou_0_5"] >= 0.8
    gate_pass = gate_mean and gate_recall

    lines: list[str] = []
    lines.append("# Eyes One-Pass — CCP-Ninja benchmark report")
    lines.append("")
    lines.append(
        f"**Dataset:** {summary['n_images']} images "
        f"({summary['n_images_failed']} failed) — "
        f"{summary['n_gt_garments_total']} GT garments, "
        f"{summary['n_predictions_total']} predictions."
    )
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append("| Metric | Threshold | Observed | Verdict |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| mean IoU | ≥ 0.60 | **{summary['mean_iou']:.3f}** | "
        f"{'✅' if gate_mean else '❌'} |"
    )
    lines.append(
        f"| recall @ IoU=0.5 | ≥ 0.80 | **{summary['recall_at_iou_0_5']:.3f}** | "
        f"{'✅' if gate_recall else '❌'} |"
    )
    lines.append(
        f"| **Overall** | — | — | {'✅ PASS — safe to flip EYES_ONE_PASS=true' if gate_pass else '❌ FAIL — keep flag false'} |"
    )
    lines.append("")
    lines.append("## IoU distribution")
    lines.append("")
    lines.append(
        f"P25 / median / P75 / P95 = "
        f"**{summary['p25_iou']:.3f}** / "
        f"**{summary['median_iou']:.3f}** / "
        f"**{summary['p75_iou']:.3f}** / "
        f"**{summary['p95_iou']:.3f}**"
    )
    lines.append("")
    lines.append(
        f"Precision @ IoU=0.5: **{summary['precision_at_iou_0_5']:.3f}** "
        f"({summary['n_matched_at_iou_0_5']} of {summary['n_predictions_total']} "
        "predictions matched a real garment)"
    )
    lines.append("")
    lines.append("## Per-class recall")
    lines.append("")
    lines.append("| Class | n GT | recall@0.5 |")
    lines.append("|---|---:|---:|")
    for cls, st in sorted(
        summary["per_class"].items(),
        key=lambda kv: (-kv[1]["n_gt"], kv[0]),
    ):
        lines.append(f"| {cls} | {st['n_gt']} | {st['recall_at_0_5']:.3f} |")
    lines.append("")
    lines.append("## Per-image detail")
    lines.append("")
    lines.append("| Image | t (s) | n_gt | n_pred | matched@0.5 | top IoU |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in per_image:
        if "error" in r:
            lines.append(
                f"| {r['image']} | — | {r.get('n_gt', 0)} | — | — | **error: {r['error'][:60]}** |"
            )
            continue
        top_iou = max((p["iou"] for p in r.get("pairs", [])), default=0.0)
        lines.append(
            f"| {r['image']} | {r['elapsed_s']:.1f} | {r['n_gt']} | "
            f"{r['n_pred']} | {r['n_matched_above_iou_05']} | {top_iou:.3f} |"
        )
    return "\n".join(lines)


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Run on at most N images (default: all in the dataset).",
    )
    parser.add_argument(
        "--out-json", type=Path, default=Path("/tmp/eyes_benchmark.json"),
    )
    parser.add_argument(
        "--out-md", type=Path, default=Path("/tmp/eyes_benchmark.md"),
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help=(
            "How many Eyes calls to issue in parallel. The Gemini fallback "
            "is cheap to parallelise (no GPU contention); the Hetzner Gemma "
            "path is single-threaded llama-server, so keep this at 1 there."
        ),
    )
    args = parser.parse_args()

    jpgs = sorted(DATASET_DIR.glob("*.jpg"))
    if args.limit:
        jpgs = jpgs[: args.limit]
    if not jpgs:
        print(f"No images found under {DATASET_DIR}.")
        return 2

    if garment_vision_service is None:
        print("garment_vision_service is None — is GEMINI_API_KEY configured?")
        return 2

    logger.info("Running on %d image(s), concurrency=%d", len(jpgs), args.concurrency)
    sem = asyncio.Semaphore(args.concurrency)

    async def _run(jpg: Path) -> dict[str, Any]:
        async with sem:
            logger.info("  -> %s", jpg.name)
            return await _benchmark_one_image(jpg)

    t_start = time.perf_counter()
    per_image = await asyncio.gather(*[_run(j) for j in jpgs])
    wall = time.perf_counter() - t_start

    summary = _aggregate(per_image)
    summary["wall_seconds"] = round(wall, 1)

    args.out_json.write_text(
        json.dumps({"summary": summary, "per_image": per_image}, indent=2)
    )
    md = _render_markdown(summary, per_image)
    args.out_md.write_text(md)
    print(md)
    print(f"\nFull JSON written to {args.out_json}")
    print(f"Markdown report at   {args.out_md}")
    print(f"Total wall time: {wall:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
