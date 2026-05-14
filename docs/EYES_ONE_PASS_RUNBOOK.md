# Eyes One-Pass — Benchmark Runbook

> Step-by-step procedure for running
> [`Eyes_OnePass_Benchmark.ipynb`](./notebooks/Eyes_OnePass_Benchmark.ipynb)
> and acting on its verdict. Companion to
> [`EYES_ONE_PASS_PROPOSAL.md`](./EYES_ONE_PASS_PROPOSAL.md).

## Prerequisites

| Item | Where to get it |
| --- | --- |
| Backend with `EYES_ONE_PASS=true` | A staging or prod deploy where the env var is set. The Emergent preview pod can be flipped temporarily with `EYES_ONE_PASS=true supervisorctl restart backend` if you want to benchmark against Gemini. |
| Auth token | Log in to the chosen backend as any user; the token is in `localStorage.dressapp.token`. |
| CCP dataset (already unpacked) | `/data/ccp-DatasetNinja/ds/` on this preview pod. On Colab: upload `ccp-DatasetNinja.rar`, run `apt-get install unrar-free && unrar-free x ccp-DatasetNinja.rar`. |
| Python deps | `ipywidgets`, `httpx`, `Pillow`, `numpy`, `pandas`. Already in the preview env. On Colab: cell 2 contains the commented-out `pip install` line — uncomment it. |

## Running locally (preview pod)

```bash
export EYES_BENCH_API_URL="https://ai-stylist-api.preview.emergentagent.com"
export EYES_BENCH_TOKEN="<paste localStorage.dressapp.token here>"
export EYES_BENCH_PHOTOS=30
# Optional: temporarily flip the flag for the preview backend
EYES_ONE_PASS=true sudo supervisorctl restart backend

jupyter notebook /app/docs/notebooks/Eyes_OnePass_Benchmark.ipynb
```

## Running on Colab (recommended for the production benchmark)

1. Upload the notebook + `ccp-DatasetNinja.rar` to a fresh Colab.
2. Run cell 1 (markdown) and cell 2 (setup) first. The dataset path
   should point at wherever you extracted CCP — defaults to
   `/data/ccp-DatasetNinja/ds`.
3. Cell 3 derives bboxes from the CCP bitmap masks. Inspect the
   per-class count to make sure nothing surprising slipped through
   (e.g. `null`, `background`).
4. **Cell 4 is the human-verification UI.** Each photo shows red
   overlay boxes; uncheck any class you don't want as a benchmark
   target (e.g. tiny accessories that aren't real garments, or
   obviously wrong bitmaps). Click *Save & Next* between photos.
   Takes ~10-20 minutes for 30 photos.
5. Cell 5 writes `benchmark_labels.json` — keep this as the gold
   reference for future re-runs (so the human verification work isn't
   wasted).
6. Cell 6 hits the Eyes API once per photo and caches the response in
   `benchmark_predictions.json`. **This is the only network-heavy
   cell** — if you Ctrl-C it, re-running picks up where it stopped
   (cached photos are skipped).
7. Cell 7 prints the per-photo summary table. Sort by mean IoU.
8. Cell 8 prints the **verdict**:

   * `VERDICT: PASS` — apply the env diff below and ship.
   * `VERDICT: FAIL` (close, pass-rate ≥ 70 %) — iterate the prompt
     (see *Tuning the prompt* below) and re-run cells 6-8.
   * `VERDICT: FAIL` (pass-rate < 70 %) — escalate to Option β
     (LoRA re-train).

## What "PASS" lets you do

Apply this diff to `deploy/.env.example`:

```diff
-EYES_ONE_PASS=false
+EYES_ONE_PASS=true
```

Then on the Hetzner box:

```bash
# Pull the change, restart backend
git pull
docker compose -f deploy/docker-compose.yml restart backend

# Verify
curl -s "${API}/api/v1/closet/analyze/version" | jq
```

The next 24-48 h are a soak window. Watch:

* `provider=gemma routing=toggle fallback=False` in `backend.err.log`
  (production should never need the Gemini fallback once Eyes is
  serving — preview will still show `provider=gemini` because preview
  cannot reach `http://eyes:7860`, by design — see
  [`PREVIEW_VS_PROD.md`](./PREVIEW_VS_PROD.md)).
* `analyze_outfit_one_pass OK garments=N elapsed_ms=...` — typical
  multi-item upload should now be ≤ 18 s instead of 50-80 s.
* Closet card render — clean cutout should swap in 5-10 s after the
  user lands on the closet page (background rembg task).

If anything regresses, the flag is recoverable with a single env flip:

```bash
EYES_ONE_PASS=false docker compose -f deploy/docker-compose.yml restart backend
```

Legacy code paths were left intact for exactly this reason.

## Tuning the prompt (between FAIL → re-run cycles)

The prompt suffix lives at
`/app/backend/app/services/garment_vision.py: SYSTEM_PROMPT_ONE_PASS_SUFFIX`.
Common levers:

* **Add more worked examples.** The current suffix has one. Two more
  (a flat-lay single garment, a 4-item outfit with overlapping
  garments) cost ~600 bytes of prompt and historically jump multi-item
  enumeration accuracy significantly.
* **Tighten the bbox rules.** If photos repeatedly underrepresent
  sleeves/hems, change "Tightly enclose the visible garment, INCLUDING
  sleeves, collars, hems." to a more imperative form
  ("Sleeves and hems MUST be inside the bbox or the row is invalid.").
* **Loosen the occlusion rule.** Default is "<20% visible → omit". If
  Eyes is over-rejecting partially occluded items, drop to "<5%".

After each prompt change:

```bash
# Reset the prediction cache so old responses don't pollute the new run
rm /app/data/benchmark_predictions.json
# Restart the backend so the new prompt is loaded
sudo supervisorctl restart backend
```

Then re-run **cells 6-8 only** in the notebook. Verified labels are
preserved between iterations.

## Escalating to Option β (LoRA re-train)

If pass-rate stays < 70 % after 2-3 prompt iterations, Option α is
fundamentally insufficient and we need new training data. Procedure:

1. Use the same CCP dataset + `derive_gt_bboxes()` from cell 3 to
   generate per-garment bboxes for the full 2,098-photo training set
   (not just the 30 we benchmark on).
2. Construct training rows in the format Eyes' LoRA expects (see the
   pipeline in the existing Eyes-v2 Colab notebook
   `docs/Eyes_v2_Merge_Quantize.ipynb`).
3. Re-train, quantise to GGUF, push to the `dressapp-eyes` container.
4. Re-run the benchmark in this notebook. Option β SHOULD pass the
   gate; if it doesn't we've hit a data ceiling and need to revisit
   the schema design (e.g. drop `is_full_frame`, simplify `region`
   shape).

## What's outside the scope of this notebook

* **Attribute accuracy** (category, sub-category, colors, etc.) is
  NOT benchmarked here — only bbox localisation. The legacy 18-field
  evaluation Colab (`docs/Eyes_v2_Smoke_Test.ipynb`) still owns that.
* **Reconstruction quality** is unchanged by this work — it's the
  same Nano Banana endpoint, just user-initiated instead of automatic.
* **rembg matte quality** is unchanged — only its timing moved
  (background task, not synchronous on `/analyze`).

## File map

```
/app/docs/EYES_ONE_PASS_PROPOSAL.md             — design doc + decisions
/app/docs/EYES_ONE_PASS_RUNBOOK.md               — this file
/app/docs/notebooks/Eyes_OnePass_Benchmark.ipynb — the actual benchmark
/app/scripts/build_eyes_benchmark_notebook.py   — regenerator for the .ipynb above
/data/ccp-DatasetNinja/                          — CCP dataset (out of git)
/app/data/benchmark_labels.json                  — human-verified GT (output of cell 5)
/app/data/benchmark_predictions.json             — cached /analyze responses (output of cell 6)
/app/data/benchmark_results.csv                  — per-pair IoU rows (output of cell 7)
```
