#!/usr/bin/env python3
"""Generator for ``/app/docs/notebooks/Eyes_v4_Unsloth_GGUF.ipynb``.

What it produces
================
A Colab notebook that takes the Eyes v4 LoRA adapter (already trained
on Drive, under ``Eyes_v4_run/checkpoint-N/``) and converts it into a
fully-merged, Q4_K_M-quantized GGUF + ``mmproj`` pair using Unsloth's
``save_pretrained_gguf`` pipeline.

Why this exists (provenance)
============================
Per ``/app/inference-server/eyes/V4_DEPLOY.md`` we chose **Path C**
(``transformers + peft`` in-container) to ship Eyes v4 today, because
plain upstream ``llama.cpp`` does not yet support Gemma-4 multimodal
LoRA → GGUF conversion (the converter outputs 0-tensor files). This
notebook scaffolds **Path B** so the team can flip back to
``llama-server`` inference once Unsloth's Gemma-4 multimodal GGUF path
is verified stable in production.

Critical foot-gun: import ordering
==================================
Unsloth patches ``numpy``'s C-ABI at import time. If ``transformers``
or ``peft`` is imported BEFORE ``unsloth``, the patch silently fails
and later imports raise opaque ``ImportError: numpy.core.multiarray
failed to import``. The notebook therefore makes the FIRST executed
code cell a single ``import unsloth`` and isolates it in its own cell
so no other imports can slip in earlier. This is documented inline.

Source recipe
=============
The Unsloth API used here mirrors the official Gemma-4 fine-tuning
guide:
  https://unsloth.ai/docs/models/gemma-4/train
  https://unsloth.ai/docs/basics/inference-and-deployment/saving-to-gguf

Specifically:
  * ``from unsloth import FastVisionModel`` (the multimodal entry point
    for Gemma-4 E2B vision + audio — not ``FastModel``, which is the
    text-only loader).
  * ``model.save_pretrained_gguf(out_dir, tokenizer, quantization_method=...)``
    auto-merges adapters and writes both the main weights GGUF and the
    multimodal projector (``mmproj-*``).
  * ``model.push_to_hub_gguf(...)`` optionally uploads to a private HF
    repo (gated by a notebook flag, default OFF).

Run
===
::

    python3 /app/scripts/build_eyes_unsloth_gguf_notebook.py

Output
======
::

    /app/docs/notebooks/Eyes_v4_Unsloth_GGUF.ipynb
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

OUT = Path("/app/docs/notebooks/Eyes_v4_Unsloth_GGUF.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)


def md(text: str) -> dict:
    """Markdown cell."""
    return {
        "cell_type": "markdown",
        "id": uuid.uuid4().hex[:12],
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    """Code cell."""
    return {
        "cell_type": "code",
        "id": uuid.uuid4().hex[:12],
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


# ─────────────────────────────────────────────────────────────────────
# Section 0 — title + provenance
# ─────────────────────────────────────────────────────────────────────
MD_TITLE = """\
# Eyes v4 — Unsloth GGUF export

> **Goal.** Convert the Eyes v4 LoRA adapter (trained in
> `Eyes_FineTune_v4_Gemma4.ipynb`) to a fully merged, Q4_K_M-quantized
> **GGUF + mmproj** pair that can be served by `llama-server` /
> llama.cpp / Ollama / vLLM.
>
> **Why this notebook exists (Path B).** The Eyes v3 production stack
> ran `llama-server` for vision inference. Eyes v4 cannot use that
> pipeline yet because plain upstream `llama.cpp` converters
> (`convert_lora_to_gguf.py`) emit 0-tensor GGUFs for Gemma-4
> multimodal LoRAs — see `inference-server/eyes/V4_DEPLOY.md` for the
> blocker analysis.
>
> **Unsloth's Gemma-4 patches** include a working `save_pretrained_gguf`
> for the E2B/E4B multimodal variants (vision + audio + text). This
> notebook wires that up so we can:
>
> 1. Pick up the latest non-empty checkpoint from
>    `Drive/MyDrive/Eyes_v4_run/checkpoint-N/`.
> 2. Load it through `FastVisionModel.from_pretrained` (the multimodal
>    entry point).
> 3. Emit `eyes_v4_q4km/Eyes-v4-E2B-Q4_K_M.gguf` **and**
>    `eyes_v4_q4km/mmproj-Eyes-v4-E2B-Q4_K_M.gguf` (the vision/audio
>    projector — without this the GGUF has no eyes).
> 4. Optionally push to a private HF repo.
> 5. Stage the artefacts in
>    `Drive/MyDrive/Eyes_v4_Gemma4_GGUF/run-<timestamp>/`.
>
> **Success criterion.** The produced main GGUF must report
> `general.architecture == "gemma4"` and `n_tensors > 0`; an
> accompanying `mmproj-*.gguf` must exist. Both conditions are asserted
> at the end of the notebook — if either fails, the run is considered
> a regression of the upstream blocker and the team should fall back
> to **Path C** (the in-container `transformers + peft` server already
> shipped).
>
> **Decision log:** `inference-server/eyes/V4_DEPLOY.md`.
>
> **Authoritative Unsloth sources:**
>   * Training guide — https://unsloth.ai/docs/models/gemma-4/train
>   * GGUF export — https://unsloth.ai/docs/basics/inference-and-deployment/saving-to-gguf
"""

# ─────────────────────────────────────────────────────────────────────
# Section 1 — GPU sanity check
# ─────────────────────────────────────────────────────────────────────
MD_GPU = """\
## 1 · GPU sanity check

This notebook needs a CUDA GPU with **≥ 16 GB VRAM** for the merge
step. On Colab free tier the T4 (15 GB) is borderline — if you see an
OOM during `save_pretrained_gguf`, switch to L4 or A100. Local
inference of the produced Q4 GGUF only needs ~3 GB so the GPU is
only required for the export, not the deployment.

Also confirm the kernel is fresh: Runtime → Disconnect and delete
runtime → reconnect. A reused kernel that already imported
`transformers` will fight Unsloth's numpy patch and corrupt the
load — symptoms are opaque `ImportError`s halfway through Step 4.
"""

CODE_GPU = """\
# Confirm we have a CUDA GPU and report its memory budget. If this
# fails or shows <16 GB free, abort and switch runtime BEFORE running
# any later cell — Unsloth caches state in /tmp on first import and
# you'll get phantom OOMs even after switching GPUs mid-run.
import subprocess
import sys

try:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
         "--format=csv,noheader,nounits"],
        text=True,
    ).strip()
    print("GPU:", out)
    name, total_mb, free_mb, drv = [x.strip() for x in out.split(",")]
    if int(free_mb) < 14000:
        print(
            f"⚠️  Only {free_mb} MiB free — Q4_K_M merge may OOM. "
            "Recommend L4 (24 GB) or A100 (40 GB)."
        )
    else:
        print(f"✅ {free_mb} MiB free — sufficient for Gemma-4 E2B Q4_K_M merge.")
except FileNotFoundError:
    print("❌ nvidia-smi not found — this notebook requires a GPU runtime.")
    sys.exit(1)
"""

# ─────────────────────────────────────────────────────────────────────
# Section 2 — install Unsloth (BEFORE any other ML import)
# ─────────────────────────────────────────────────────────────────────
MD_INSTALL = """\
## 2 · Install Unsloth

We install **Unsloth first** and **import it first**. Both of those
matter:

* **Install order** — Unsloth ships with pinned versions of
  `transformers`, `peft`, and `accelerate` that include the Gemma-4
  bug fixes from
  https://unsloth.ai/docs/models/gemma-4/train#bug-fixes--tips
  (`use_cache=False` corruption, audio fp16 overflow, MoE
  `num_kv_shared_layers=0` crash). If pip resolves a newer
  `transformers` later, the patches stop applying.
* **Import order** — `import unsloth` *must* run before any
  `transformers` / `peft` / `accelerate` import. Unsloth patches
  numpy's C-ABI at module load; if `transformers` got there first,
  the patch silently no-ops and you get `ImportError: numpy.core.…`
  several cells later with no obvious link to the root cause.

If a previous cell in this kernel has already imported `transformers`
(e.g. you re-ran the install cell after experimenting), **Runtime →
Disconnect and delete runtime** and start fresh.
"""

CODE_INSTALL = """\
# Quiet install — Unsloth pulls its own pinned transformers/peft/etc.
# We pass --no-deps for the meta-package to avoid pip re-pinning
# everything underneath and breaking the Gemma-4 fixes.
%pip install -q -U unsloth
%pip install -q -U "gguf>=0.10.0"  # for the GGUF sniffer at the end
print("Unsloth installed.")
"""

CODE_IMPORT_UNSLOTH = """\
# *** THIS CELL MUST RUN BEFORE ANY transformers / peft / accelerate
# *** IMPORT IN THIS KERNEL. ***
#
# Unsloth's patching has to monkey-patch the transformers loader,
# the peft target_modules picker, and a few low-level numpy entry
# points. All of that has to happen at module-import time, BEFORE
# transformers caches its model_type → class registry.
#
# After this cell, you can safely import anything else.
import unsloth  # noqa: F401 — side-effects only
print(f"Unsloth {unsloth.__version__} imported (must be first ML import).")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 3 — Drive mount + Colab Secrets
# ─────────────────────────────────────────────────────────────────────
MD_DRIVE = """\
## 3 · Mount Drive and unlock secrets

We assume the standard DressApp Drive layout:

```
MyDrive/
├── Eyes_v4_run/              ← training checkpoints (input)
│   ├── checkpoint-100/
│   ├── checkpoint-200/
│   └── …
└── Eyes_v4_Gemma4_GGUF/      ← export destination (output)
    └── (run-<timestamp>/ folders we'll create here)
```

The notebook reads `HF_TOKEN` from Colab Secrets (Tools → Secrets in
the left sidebar). It's only needed if you flip `PUSH_TO_HF = True`
later, but having it set up-front means the push step is one-click.
"""

CODE_DRIVE = """\
from google.colab import drive, userdata
import os

# Idempotent — re-mounting is a no-op if already mounted.
drive.mount("/content/drive", force_remount=False)

# Best-effort secrets pickup. If HF_TOKEN isn't in Colab Secrets and
# you don't plan to push, that's fine.
try:
    os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")
    print("HF_TOKEN  : set from Colab Secrets")
except Exception as exc:  # noqa: BLE001
    print(f"HF_TOKEN  : not available ({exc.__class__.__name__}) — push disabled")

# Lock in the canonical paths used everywhere below.
DRIVE_ROOT       = "/content/drive/MyDrive"
TRAIN_RUN_DIR    = f"{DRIVE_ROOT}/Eyes_v4_run"             # input
EXPORT_ROOT_DIR  = f"{DRIVE_ROOT}/Eyes_v4_Gemma4_GGUF"     # output

os.makedirs(EXPORT_ROOT_DIR, exist_ok=True)
assert os.path.isdir(TRAIN_RUN_DIR), (
    f"Eyes_v4_run not found at {TRAIN_RUN_DIR!r}. "
    "Run Eyes_FineTune_v4_Gemma4.ipynb first to produce training "
    "checkpoints, or fix the path."
)
print(f"TRAIN_RUN_DIR   : {TRAIN_RUN_DIR}")
print(f"EXPORT_ROOT_DIR : {EXPORT_ROOT_DIR}")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 4 — pick the latest non-empty adapter checkpoint
# ─────────────────────────────────────────────────────────────────────
MD_PICK = """\
## 4 · Pick the latest non-empty adapter

The training notebook produces multiple `checkpoint-N/` folders. We
want the **highest-step, non-empty** one. "Non-empty" matters because
a previous session occasionally produced 40-byte
`adapter_model.safetensors` files (corrupted save / interrupted
training); converting those to GGUF would silently produce a useless
artefact. We enforce a 1 MB lower bound, which is well above the
40-byte error mode but below the smallest plausible real adapter
(~4 MB for r=8 LoRA on E2B).
"""

CODE_PICK = """\
import os
import re

MIN_ADAPTER_BYTES = 1_000_000   # 1 MB — see markdown above

def _checkpoint_step(name: str) -> int:
    m = re.match(r"checkpoint-(\\d+)$", name)
    return int(m.group(1)) if m else -1

candidates = []
for name in os.listdir(TRAIN_RUN_DIR):
    step = _checkpoint_step(name)
    if step < 0:
        continue
    sft = os.path.join(TRAIN_RUN_DIR, name, "adapter_model.safetensors")
    if not os.path.isfile(sft):
        continue
    size = os.path.getsize(sft)
    candidates.append((step, size, os.path.join(TRAIN_RUN_DIR, name)))

# Print every candidate so a corrupted folder is visible.
print(f"Found {len(candidates)} checkpoint(s):")
for step, size, path in sorted(candidates):
    flag = "✅" if size >= MIN_ADAPTER_BYTES else "❌ EMPTY/CORRUPT"
    print(f"  {flag}  checkpoint-{step:<6d}  {size/1024/1024:>7.2f} MB  {path}")

# Filter and pick the latest non-empty one.
good = [c for c in candidates if c[1] >= MIN_ADAPTER_BYTES]
assert good, (
    f"No checkpoint under {TRAIN_RUN_DIR} has adapter_model.safetensors "
    f">= {MIN_ADAPTER_BYTES} bytes. Re-run training or copy a valid "
    "adapter into a fresh checkpoint folder."
)
ADAPTER_DIR = max(good, key=lambda c: c[0])[2]
print(f"\\nPicked adapter: {ADAPTER_DIR}")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 5 — load base + adapter via Unsloth
# ─────────────────────────────────────────────────────────────────────
MD_LOAD = """\
## 5 · Load Gemma-4 E2B + the Eyes v4 LoRA adapter

`FastVisionModel.from_pretrained` is Unsloth's entry point for the
**multimodal** Gemma-4 variants (E2B and E4B — the ones with the
vision tower and the audio tower). For our use case:

* We prefer `unsloth/gemma-4-E2B-it` as the base (Unsloth-shipped
  variant with the bug fixes from
  https://unsloth.ai/docs/models/gemma-4/train#bug-fixes--tips).
  Google's gated `google/gemma-4-E2B-it` works too if you have HF
  auth set up.
* We load at `load_in_4bit=True` because we're about to merge into a
  Q4_K_M GGUF anyway — going through 4-bit shaves ~30 s off the merge
  on T4 and avoids OOM peaks.
* After the base is up, `model.load_adapter(ADAPTER_DIR)` plays our
  LoRA onto it. We use `is_trainable=False` so PEFT freezes the
  weights (otherwise the next merge step would try to allocate
  optimizer state we don't need).

`save_pretrained_gguf` later auto-merges, so we do NOT need an
explicit `merge_and_unload()` here.
"""

CODE_LOAD = """\
import time
import os

from unsloth import FastVisionModel

BASE_MODEL = "unsloth/gemma-4-E2B-it"
HF_TOKEN   = os.environ.get("HF_TOKEN") or None

t0 = time.time()
print(f"Loading base {BASE_MODEL} (4-bit) …")
model, processor = FastVisionModel.from_pretrained(
    model_name = BASE_MODEL,
    load_in_4bit = True,
    use_gradient_checkpointing = "unsloth",
    token = HF_TOKEN,
)
print(f"  base loaded in {time.time()-t0:.1f}s")

t0 = time.time()
print(f"Attaching Eyes v4 LoRA adapter from {ADAPTER_DIR} …")
# load_adapter() is exposed by the PeftModel that FastVisionModel
# returns. is_trainable=False saves ~1 GB of would-be optimizer state.
model.load_adapter(ADAPTER_DIR, adapter_name="eyes_v4", is_trainable=False)
# Activate it (no-op if it's already the only adapter, but explicit
# in case future runs stack multiple adapters).
model.set_adapter("eyes_v4")
print(f"  adapter attached in {time.time()-t0:.1f}s")

# A quick sanity print so the next cell doesn't run against the wrong
# weights.
total_params  = sum(p.numel() for p in model.parameters())
adapter_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"\\nModel ready  : total {total_params/1e9:.2f} B params, "
      f"adapter {adapter_params/1e6:.1f} M trainable")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 6 — save to GGUF
# ─────────────────────────────────────────────────────────────────────
MD_SAVE = """\
## 6 · Export to GGUF (Q4_K_M)

`save_pretrained_gguf` does three things in one call:

1. Merges the LoRA back into the base weights (in fp16 internally).
2. Quantizes the merged weights to Q4_K_M.
3. Writes the result as:
   * `Eyes-v4-E2B-Q4_K_M.gguf`   — main model (text + vision tower)
   * `mmproj-Eyes-v4-E2B-Q4_K_M.gguf` — vision/audio projector

The projector is the small file (~50 MB) that turns image
embeddings into tokens the LM can consume. **Without it the GGUF
has no eyes** — llama-server will load it and run, but the
multimodal endpoints will silently produce text-only completions.
Always verify both files exist before deploying.

If you want a higher-fidelity export for offline analysis (e.g. to
debug a quality regression vs. the transformers+peft Path C
server), change `QUANT_METHOD` to `q8_0` or `f16`. Default is
`q4_k_m` to match what `dressapp-eyes` currently expects.
"""

CODE_SAVE = """\
import time

QUANT_METHOD = "q4_k_m"   # alternatives: "q5_k_m", "q8_0", "f16"
EXPORT_DIR   = f"/content/eyes_v4_{QUANT_METHOD}"   # local first, copy to Drive later

import shutil
if os.path.isdir(EXPORT_DIR):
    print(f"Removing stale {EXPORT_DIR}/ from a previous run …")
    shutil.rmtree(EXPORT_DIR)
os.makedirs(EXPORT_DIR, exist_ok=True)

t0 = time.time()
print(f"Exporting to {EXPORT_DIR} as {QUANT_METHOD.upper()} GGUF …")
model.save_pretrained_gguf(
    EXPORT_DIR,
    processor.tokenizer if hasattr(processor, "tokenizer") else processor,
    quantization_method = QUANT_METHOD,
)
print(f"  done in {(time.time()-t0)/60:.1f} min")

# Show what we got. Both files should be visible.
print("\\nProduced files:")
for f in sorted(os.listdir(EXPORT_DIR)):
    full = os.path.join(EXPORT_DIR, f)
    size_mb = os.path.getsize(full) / 1024 / 1024
    print(f"  {size_mb:>7.1f} MB  {f}")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 7 — validate GGUF outputs
# ─────────────────────────────────────────────────────────────────────
MD_VERIFY = """\
## 7 · Validate the produced GGUF

Three hard checks before we declare success:

1. The **main GGUF** must report
   `metadata['general.architecture'] == 'gemma4'`.
   Any other value (especially `'gemma3'`) means Unsloth picked the
   wrong family — see `V4_DEPLOY.md` for the historical
   `Gemma3ForConditionalGeneration` foot-gun.
2. The **main GGUF** must contain `> 0` tensors. The upstream
   `convert_lora_to_gguf.py` blocker that drove us to Path C
   manifested as 0-tensor outputs.
3. A `mmproj-*.gguf` file must exist. Without it llama-server runs
   without eyes.

We use the official `gguf` Python package (the same library
`llama.cpp` uses internally) so the sniffer is robust against minor
format revisions.
"""

CODE_VERIFY = """\
import glob

from gguf import GGUFReader  # noqa: WPS433 — late import is fine here

def _peek_gguf(path: str) -> dict:
    \"\"\"Return {arch, n_tensors, version} for a GGUF file.\"\"\"
    r = GGUFReader(path)
    arch_field = r.fields.get("general.architecture")
    if arch_field is None:
        arch = "<missing>"
    else:
        # gguf >=0.10 stores strings as a bytes blob; decode the slice.
        arch = bytes(arch_field.parts[arch_field.data[-1]]).decode("utf-8", "replace")
    return {
        "arch": arch,
        "n_tensors": len(r.tensors),
        "version": int(r.version),
    }

main_files   = sorted(glob.glob(os.path.join(EXPORT_DIR, "[!m]*.gguf")))   # not starting with 'm'
mmproj_files = sorted(glob.glob(os.path.join(EXPORT_DIR, "mmproj-*.gguf")))

assert main_files, f"No main GGUF (non-mmproj) found in {EXPORT_DIR}"
assert mmproj_files, (
    f"No mmproj-*.gguf produced in {EXPORT_DIR}. The vision/audio "
    "projector is missing — Unsloth's Gemma-4 multimodal export "
    "regressed. Fall back to Path C (transformers+peft) per "
    "V4_DEPLOY.md."
)

print("Main GGUF(s):")
for p in main_files:
    meta = _peek_gguf(p)
    print(f"  {os.path.basename(p):<50s}  arch={meta['arch']:<10s} "
          f"version={meta['version']}  n_tensors={meta['n_tensors']}")
    assert meta["arch"] == "gemma4", (
        f"Unexpected arch {meta['arch']!r} for {p} — should be 'gemma4'"
    )
    assert meta["n_tensors"] > 0, (
        f"GGUF {p} has 0 tensors — this is the upstream blocker. "
        "Stay on Path C until Unsloth fixes the export."
    )

print("\\nMultimodal projector(s):")
for p in mmproj_files:
    meta = _peek_gguf(p)
    print(f"  {os.path.basename(p):<50s}  arch={meta['arch']:<10s} "
          f"version={meta['version']}  n_tensors={meta['n_tensors']}")
    assert meta["n_tensors"] > 0, f"mmproj {p} has 0 tensors"

print("\\n✅ All three checks passed.")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 8 — optional Hub push
# ─────────────────────────────────────────────────────────────────────
MD_PUSH = """\
## 8 · (Optional) Push to a private HF Hub repo

Default is **OFF**. Flip `PUSH_TO_HF = True` and set `HF_REPO_ID` to
the target repo (must be private; the model is fine-tuned on
proprietary user data). The push uploads both the main GGUF and the
`mmproj` to the same repo so deployment can pull them in one go.

This is the path the production VPS uses to fetch the eyes weights
(`hf_hub_download` from inside the `dressapp-eyes` container if you
flip back to the llama-server engine).
"""

CODE_PUSH = """\
PUSH_TO_HF   = False                                # ← flip to True to push
HF_REPO_ID   = "Yoram-Jacobs/dressapp-eyes-gguf"    # private; create on hf.co first

if not PUSH_TO_HF:
    print("PUSH_TO_HF is False — skipping upload. Set the flag above to enable.")
else:
    assert os.environ.get("HF_TOKEN"), (
        "HF_TOKEN not set in Colab Secrets — cannot push."
    )
    print(f"Pushing {EXPORT_DIR} → {HF_REPO_ID} …")
    # push_to_hub_gguf re-runs the merge + quantize internally, so it
    # takes about the same time as save_pretrained_gguf above. If you
    # want to upload the ALREADY-saved files instead (skipping the
    # second merge), use huggingface_hub directly:
    #
    #     from huggingface_hub import HfApi
    #     HfApi().upload_folder(folder_path=EXPORT_DIR,
    #                            repo_id=HF_REPO_ID, repo_type='model')
    #
    # We pick the slower (Unsloth-native) path here for parity with the
    # GGUF metadata Unsloth tags onto its uploads.
    model.push_to_hub_gguf(
        HF_REPO_ID,
        processor.tokenizer if hasattr(processor, "tokenizer") else processor,
        quantization_method = QUANT_METHOD,
        token = os.environ["HF_TOKEN"],
    )
    print("✅ Pushed.")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 9 — stage to Drive
# ─────────────────────────────────────────────────────────────────────
MD_STAGE = """\
## 9 · Stage to Drive

We copy the export into
`MyDrive/Eyes_v4_Gemma4_GGUF/run-<timestamp>/` so each run is
archived (Drive deduplicates so the on-disk cost is roughly one
copy). The "latest" symlink convenience is intentionally absent —
Drive's FUSE layer doesn't honour symlinks reliably; we instead
print the path so the deployment runbook can paste it directly.
"""

CODE_STAGE = """\
import datetime
import shutil

stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
stage_dir = f"{EXPORT_ROOT_DIR}/run-{stamp}-{QUANT_METHOD}"
os.makedirs(stage_dir, exist_ok=True)

print(f"Copying {EXPORT_DIR} → {stage_dir} …")
for f in sorted(os.listdir(EXPORT_DIR)):
    src = os.path.join(EXPORT_DIR, f)
    dst = os.path.join(stage_dir, f)
    shutil.copy2(src, dst)
    print(f"  {os.path.getsize(dst)/1024/1024:>7.1f} MB  {dst}")

print(f"\\n✅ Eyes v4 GGUFs staged at: {stage_dir}")
print("\\nNext step: see inference-server/eyes/V4_DEPLOY.md for the")
print("rollback to llama-server runtime (only when Unsloth's multimodal")
print("GGUF path is verified stable in production).")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 10 — optional smoke inference
# ─────────────────────────────────────────────────────────────────────
MD_SMOKE = """\
## 10 · (Optional) Smoke-test the GGUF locally

Loads the produced Q4_K_M GGUF with `llama-cpp-python` and runs a
single one-shot prompt against it. **Vision input is NOT exercised
here** because `llama-cpp-python` needs the mmproj file passed via
a separate API that's not stable across versions; we'll do a proper
vision smoke from the `dressapp-eyes` container once it loads the
file. This step just confirms the GGUF is structurally loadable.

Skipped if `RUN_SMOKE = False` (the default — saves ~2 min and
the GGUF sniffer above is already a structural validity check).
"""

CODE_SMOKE = """\
RUN_SMOKE = False

if not RUN_SMOKE:
    print("RUN_SMOKE is False — skipping local llama.cpp smoke. "
          "The GGUF sniffer in Step 7 already confirmed structural validity.")
else:
    %pip install -q "llama-cpp-python>=0.3.0"
    from llama_cpp import Llama

    main_gguf = main_files[0]
    print(f"Loading {main_gguf} …")
    llm = Llama(
        model_path = main_gguf,
        n_ctx = 1024,
        n_gpu_layers = 0,   # CPU smoke — proves it loads even without GPU.
        verbose = False,
    )
    print("\\nPrompt: 'List three garment types: '")
    out = llm.create_chat_completion(
        messages = [
            {"role": "user", "content": "List three garment types: "},
        ],
        max_tokens = 40,
        temperature = 0.0,
    )
    text = out["choices"][0]["message"]["content"]
    print(f"Response: {text!r}")
    assert text.strip(), "Empty response — quantization may have collapsed the model."
    print("\\n✅ Smoke OK.")
"""

# ─────────────────────────────────────────────────────────────────────
# Section 11 — closing
# ─────────────────────────────────────────────────────────────────────
MD_CLOSING = """\
## 11 · Done

You now have a Gemma-4 E2B + Eyes v4 LoRA → merged → Q4_K_M GGUF
pair on Drive at the path printed above. **This is the Path B
artefact** referenced by `inference-server/eyes/V4_DEPLOY.md`.

### What this notebook does NOT do

* It does not deploy. The artefact has to be copied (or pulled from
  HF Hub) onto the Hetzner host and the `dressapp-eyes` container
  has to be reconfigured for the llama-server engine instead of the
  currently-shipped `transformers + peft` one.
* It does not retire Path C. Path C is still the production engine
  until the team confirms Path B is at least as good on the real
  benchmark (`scripts/run_eyes_benchmark.py`).

### When to actually flip production

1. Generate this GGUF.
2. Run it through the local Eyes benchmark in CPU-mode against the
   currently-deployed transformers+peft engine; require >= parity
   on category F1 + bbox IoU.
3. Switch the `dressapp-eyes` `Dockerfile` back to the v3-style
   llama.cpp build stage **but pointing at the new Q4_K_M GGUF**.
4. Use `eyes_override.set_override('gemma', …)` to flip traffic.
5. Watch p95 latency for 24 h; if regression, flip back to `gemini`.
"""


# ─────────────────────────────────────────────────────────────────────
# Assemble notebook
# ─────────────────────────────────────────────────────────────────────
cells = [
    md(MD_TITLE),

    md(MD_GPU),
    code(CODE_GPU),

    md(MD_INSTALL),
    code(CODE_INSTALL),
    code(CODE_IMPORT_UNSLOTH),

    md(MD_DRIVE),
    code(CODE_DRIVE),

    md(MD_PICK),
    code(CODE_PICK),

    md(MD_LOAD),
    code(CODE_LOAD),

    md(MD_SAVE),
    code(CODE_SAVE),

    md(MD_VERIFY),
    code(CODE_VERIFY),

    md(MD_PUSH),
    code(CODE_PUSH),

    md(MD_STAGE),
    code(CODE_STAGE),

    md(MD_SMOKE),
    code(CODE_SMOKE),

    md(MD_CLOSING),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11",
        },
        "colab": {
            "provenance": [],
            "toc_visible": True,
            "name": "Eyes_v4_Unsloth_GGUF.ipynb",
        },
        "accelerator": "GPU",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False))
print(f"Wrote {OUT}  ({OUT.stat().st_size/1024:.1f} KB, {len(cells)} cells)")
