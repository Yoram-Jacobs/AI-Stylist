#!/usr/bin/env python3
"""Generator for ``/app/docs/notebooks/Eyes_FineTune_v4_Gemma4.ipynb``.

Reproduces Eyes from scratch on the **correct** Gemma-4 E2B base
(``google/gemma-4-E2B-it``), using TWO datasets:

* DeepFashion-Multimodal (Kaggle, ~12 k images)
* CCP-DatasetNinja (~2 k images, already mounted in user's Drive)

Replaces the prior v4-merged checkpoint produced by an earlier agent
which was loaded with ``Gemma3ForConditionalGeneration`` — wrong family
entirely. Gemma 4 is a NEW family released March-April 2026, not a
revision of Gemma-3 or Gemma-3n. The HF model card for
``google/gemma-4-E2B-it`` instructs loading via the Auto classes
(``AutoProcessor`` + ``AutoModelForMultimodalLM``), so that's what we
do here. The conversation roles are gemma-4's native
``system`` / ``user`` / ``assistant`` (NOT the Gemma-3 ``model`` role),
and we explicitly disable Gemma-4's built-in thinking mode so Eyes
emits a clean JSON array with no ``<|think|>`` reasoning trace.

Auth is via Colab Secrets — the user has already defined
``HF_TOKEN``, ``KAGGLE_USERNAME``, ``KAGGLE_KEY`` in the Colab sidebar
(Tools → Secrets). No file uploads or hidden prompts are needed.

Run::

    python3 /app/scripts/build_eyes_finetune_v4_notebook.py

Output::

    /app/docs/notebooks/Eyes_FineTune_v4_Gemma4.ipynb
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/app/docs/notebooks/Eyes_FineTune_v4_Gemma4.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)


def md(text):
    return {"cell_type": "markdown", "metadata": {},
            "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {},
            "execution_count": None, "outputs": [],
            "source": text.splitlines(keepends=True)}


# ─────────────────────────────────────────────────────────────
# Section 0 — header
# ─────────────────────────────────────────────────────────────
MD_TITLE = """\
# Eyes v4 — Fine-Tune Gemma-4 E2B on DeepFashion + CCP

> **Objective.** Train a fresh Eyes LoRA on top of Google's official
> `google/gemma-4-E2B-it` checkpoint so that a single Eyes call emits
> a JSON array `[{label, category, region.bbox}, …]` covering every
> visible garment, accessory, or footwear item.
>
> **Why a clean restart.** The previous `Eyes_v3_*_merged` folder was
> produced by a prior agent that loaded the base with
> `Gemma3ForConditionalGeneration` — wrong family entirely. Gemma 4
> is a NEW family (released March-April 2026), architecturally
> different from both Gemma-3 and Gemma-3n: it has its own native
> `system` role, an `enable_thinking` flag, a hybrid local/global
> attention pattern, Per-Layer Embeddings (PLE) on the small
> variants, and on E2B/E4B a separate audio tower. Loading it with
> the wrong class silently dropped projector tensors and corrupted
> the checkpoint past recovery. We start over here from the official
> HF Hub release.
>
> **Authoritative loading recipe** (from the HF model card + dev.to
> fine-tuning guide):
> ```python
> from transformers import AutoProcessor, AutoModelForImageTextToText
> processor = AutoProcessor.from_pretrained("google/gemma-4-E2B-it")
> model = AutoModelForImageTextToText.from_pretrained(
>     "google/gemma-4-E2B-it", dtype="auto", device_map="auto")
> ```
> We pick `AutoModelForImageTextToText` (vision-language head) over
> `AutoModelForMultimodalLM` (text+image+audio head) because Eyes is
> vision-only — no audio. The dev.to QLoRA recipe uses the same
> class. Either would work; this is the narrower correct choice.
> No hand-rolled `Gemma4*ForConditionalGeneration` import — the Auto
> classes dispatch to whatever the installed transformers release
> ships as the vision-language head for Gemma-4. Requires
> `transformers >= 5.5.0`.
>
> **Target runtime.** Colab Pro+ A100 (40 GB). ≈ 14 k images × 2
> epochs with bf16 + LoRA-only training → roughly 25–35 min wall.

## Inputs

| Asset | Source / Path |
| --- | --- |
| Base model (gated) | `google/gemma-4-E2B-it` on HF Hub |
| DeepFashion-Multimodal | Kaggle dataset `silverstone1903/deep-fashion-multimodal` |
| CCP-DatasetNinja | `/content/drive/MyDrive/ccp-DatasetNinja` |

## Outputs (written to Drive)

| Artifact | Path |
| --- | --- |
| Merged bf16 (HF format) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_Gemma4_merged/` |
| Text-model GGUF (Q4_K_M) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_Gemma4-Q4_K_M.gguf` |
| Vision projector GGUF | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/mmproj-Eyes_v4_Gemma4-f16.gguf` |
| Training run dir | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_run/` |

## What "freeze the weights" means here

We use **two complementary mechanisms** to keep the base model
weights pristine and only train a thin LoRA adapter on the text
decoder's attention/MLP projections:

1. An explicit `requires_grad = False` pass at load time on every
   parameter outside `language_model.*` (so the vision tower, audio
   tower, multimodal projector, PLE banks, and any other auxiliary
   submodules stay frozen no matter what).
2. PEFT-LoRA on top of that — which by construction freezes every
   base parameter (whether or not it was already frozen in step 1)
   and only flows gradient through the rank-16 adapter matrices
   wrapped around the text decoder's `q/k/v/o/gate/up/down_proj`
   linears.

Belt-and-braces: even a future cell that calls `.train()` or
`.requires_grad_(True)` on the whole model would still leave the
non-text modules untouched, because LoRA is the only thing that
holds trainable params at that point.

## Authentication — Colab Secrets (zero prompts)

This notebook reads three secrets from the Colab sidebar (Tools →
Secrets — toggle "Notebook access" ON for each):

* `HF_TOKEN` — read-access token from
  <https://huggingface.co/settings/tokens>. The HF account behind the
  token MUST have accepted the Gemma license on
  <https://huggingface.co/google/gemma-4-E2B-it> first.
* `KAGGLE_USERNAME` — your Kaggle username.
* `KAGGLE_KEY` — the `key` value from a Kaggle API token JSON.

No file uploads, no `getpass()` prompts — the runtime grabs all
three secrets at startup and exports them as env vars where the
`huggingface_hub` and `kaggle` CLIs expect them.
"""


# ─────────────────────────────────────────────────────────────
# Section 1 — Mount Drive + GPU
# ─────────────────────────────────────────────────────────────
MD_DRIVE = """\
---

## 1. Mount Drive + verify A100
"""

CODE_MOUNT = """\
from google.colab import drive
drive.mount('/content/drive', force_remount=False)
"""

CODE_GPU = """\
# Confirm A100 40 GB (or H100 80 GB if you upgraded). On smaller GPUs
# you'd need to enable QLoRA — see the commented-out 4-bit block in
# the model-load cell below.
!nvidia-smi
"""

CODE_PATHS = """\
import pathlib

BASE_DIR    = pathlib.Path('/content/drive/MyDrive/DressApp_Gemma4_E2B_Training')
CCP_DIR     = pathlib.Path('/content/drive/MyDrive/ccp-DatasetNinja')
DF_DIR      = pathlib.Path('/content/deepfashion_mm')           # Kaggle extracts here
OUT_RUN     = BASE_DIR / 'Eyes_v4_run'
OUT_MERGED  = BASE_DIR / 'Eyes_v4_Gemma4_merged'
OUT_GGUF    = BASE_DIR / 'Eyes_v4_Gemma4-Q4_K_M.gguf'
OUT_MMPROJ  = BASE_DIR / 'mmproj-Eyes_v4_Gemma4-f16.gguf'
for p in (BASE_DIR, OUT_RUN, DF_DIR.parent):
    p.mkdir(parents=True, exist_ok=True)

assert CCP_DIR.exists(), f'CCP-DatasetNinja missing at {CCP_DIR}'
print('Drive paths:')
print('   base dir       :', BASE_DIR)
print('   CCP corpus     :', CCP_DIR)
print('   DeepFashion dl :', DF_DIR, '(downloaded in section 3)')
print('   v4 outputs ->  :', OUT_MERGED, '+', OUT_GGUF, '+', OUT_MMPROJ)
"""


# ─────────────────────────────────────────────────────────────
# Section 2 — Dependencies
# ─────────────────────────────────────────────────────────────
MD_DEPS = """\
---

## 2. Dependencies — minimal upgrade

Per the dev.to Gemma-4 practical guide (April 2026):

```
pip install -U transformers torch torchvision accelerate timm
```

`transformers >= 5.5.0` is required to know about Gemma-4. `timm` is
needed for the vision encoder's image preprocessing. We add `peft`
(for LoRA), `kaggle` (for the DeepFashion download), and
`huggingface_hub[cli]` (for gated-model auth).

We do **not** pin `numpy` or `Pillow` — Colab now defaults to
Python 3.12 and any older pin will break `torchvision`/`transformers`
imports.

If an import fails after running this cell, do
**Runtime → Restart session** (poisoned `sys.modules`) and re-run
from cell 1.
"""

CODE_DEPS = """\
%pip install -q --upgrade pip
%pip install -q -U 'transformers>=5.5.0' torch torchvision accelerate timm
%pip install -q -U peft
%pip install -q 'kaggle' 'huggingface_hub[cli]'

import transformers, peft, accelerate, torch, numpy, PIL
print('python      :', __import__('sys').version.split()[0])
print('numpy       :', numpy.__version__)
print('Pillow      :', PIL.__version__)
print('torch       :', torch.__version__, 'cuda', torch.version.cuda)
print('transformers:', transformers.__version__)
print('peft        :', peft.__version__)
print('accelerate  :', accelerate.__version__)
print('bf16 ok?    :', torch.cuda.is_bf16_supported())

# Sanity: transformers must be new enough to know about Gemma-4.
from transformers import AutoModelForImageTextToText  # noqa: F401
print('AutoModelForImageTextToText import : OK')

# Hard-stop if transformers is too old.
from packaging.version import Version
assert Version(transformers.__version__) >= Version('5.5.0'), \\
    f'transformers {transformers.__version__} is too old for Gemma-4 (need >= 5.5.0)'
"""


# ─────────────────────────────────────────────────────────────
# Section 3 — Auth via Colab Secrets + DeepFashion download
# ─────────────────────────────────────────────────────────────
MD_AUTH = """\
---

## 3. Auth via Colab Secrets + Kaggle download

This cell expects three secrets to be present in the Colab sidebar
(Tools → Secrets), each with "Notebook access" toggled ON:

| Secret name        | What it is                              |
| ------------------ | --------------------------------------- |
| `HF_TOKEN`         | HF read token (Gemma license accepted)  |
| `KAGGLE_USERNAME`  | Your Kaggle username                    |
| `KAGGLE_KEY`       | Your Kaggle API key                     |

If any of them is missing, the cell will raise a clear error
pointing at the sidebar so you know exactly what to add — there is
no file upload and no hidden-input prompt.
"""

CODE_HF_AUTH = """\
from google.colab import userdata
from huggingface_hub import login as hf_login

try:
    hf_token = userdata.get('HF_TOKEN')
except userdata.SecretNotFoundError as e:
    raise RuntimeError(
        \"Colab secret 'HF_TOKEN' is missing. Open Tools -> Secrets, \"
        \"add HF_TOKEN with your HuggingFace read token, and toggle \"
        \"'Notebook access' ON.\"
    ) from e

hf_login(token=hf_token, add_to_git_credential=False)
print('Logged into HF Hub.')
"""

CODE_KAGGLE_AUTH = """\
import os
from google.colab import userdata

for key in ('KAGGLE_USERNAME', 'KAGGLE_KEY'):
    try:
        os.environ[key] = userdata.get(key)
    except userdata.SecretNotFoundError as e:
        raise RuntimeError(
            f\"Colab secret '{key}' is missing. Open Tools -> Secrets, \"
            f\"add {key}, and toggle 'Notebook access' ON.\"
        ) from e

print(f'Kaggle creds in env for user: {os.environ[\"KAGGLE_USERNAME\"]}')
"""

CODE_DF_DOWNLOAD = """\
# Download + unzip DeepFashion-Multimodal.
# Kaggle dataset URL: https://www.kaggle.com/datasets/silverstone1903/deep-fashion-multimodal
import subprocess, pathlib

if not (DF_DIR / '_done').exists():
    subprocess.run([
        'kaggle', 'datasets', 'download',
        '-d', 'silverstone1903/deep-fashion-multimodal',
        '-p', str(DF_DIR.parent),
        '--unzip',
    ], check=True)
    # Some Kaggle datasets unpack into a versioned subfolder; flatten if so.
    nested = [p for p in DF_DIR.parent.iterdir() if p.is_dir() and p.name.startswith('deep')]
    if nested and not (DF_DIR / 'images').exists():
        DF_DIR.mkdir(exist_ok=True)
        for p in nested[0].iterdir():
            p.rename(DF_DIR / p.name)
    (DF_DIR / '_done').touch()

print('DeepFashion-Multimodal contents:')
for p in sorted(DF_DIR.iterdir())[:20]:
    print('  ', p.name, '(dir)' if p.is_dir() else f'({p.stat().st_size // 1024} KB)')
"""


# ─────────────────────────────────────────────────────────────
# Section 4 — Load Gemma-4 + freeze everything except text-decoder
# ─────────────────────────────────────────────────────────────
MD_LOAD = """\
---

## 4. Load `google/gemma-4-E2B-it` and aggressively freeze

The dev.to QLoRA recipe for Gemma-4 fine-tuning uses
`AutoModelForImageTextToText` — that's the vision-language head and
the right Auto class for our use case (Eyes is image+text, no
audio). Both Auto factories dispatch to the same concrete class for
Gemma-4 in transformers 5.5+, but the narrower one is the dev-blog
canonical recipe.

Right after loading we do a **two-step parameter freeze**:

1. Print the full named-parameters tree, grouped by top-level
   submodule (vision tower, audio tower, multimodal projector, PLE
   banks, language model, ...). This is a diagnostic for any future
   debugging — Gemma-4's exact submodule names are
   version-dependent.
2. Set `requires_grad=False` on every parameter whose name does NOT
   live inside `language_model.*`. PEFT-LoRA will further freeze the
   `language_model.*` base weights too; this pass is the
   belt-and-braces guarantee that nothing outside the text decoder
   ever sees a gradient.
"""

CODE_LOAD = """\
import torch
from collections import Counter
from transformers import AutoProcessor, AutoModelForImageTextToText

BASE_MODEL = 'google/gemma-4-E2B-it'

processor = AutoProcessor.from_pretrained(BASE_MODEL)
model = AutoModelForImageTextToText.from_pretrained(
    BASE_MODEL,
    dtype=torch.bfloat16,                 # transformers 5.x: 'dtype' (was torch_dtype)
    device_map={'': 0},
    attn_implementation='eager',          # safest for cross-attention LoRA
)

# Gemma-4 supports variable image resolution via a visual token
# budget (70 / 140 / 280 / 560 / 1120 tokens per image). Clothing
# detection benefits from fine-grained detail, so we use the
# highest budget. If the processor exposes a different knob name in
# your transformers version, this is a no-op.
for knob in ('vision_token_budget', 'image_token_budget', 'num_image_tokens'):
    if hasattr(processor, knob):
        try:
            setattr(processor, knob, 1120)
            print(f'Set processor.{knob} = 1120 (max detail)')
            break
        except (AttributeError, TypeError):
            pass

# ---- Diagnostic: print top-level submodule param counts ----
top_buckets = Counter()
for name, p in model.named_parameters():
    top = name.split('.', 1)[0]
    top_buckets[top] += p.numel()
print('Top-level submodules and their param counts (millions):')
for name, n in sorted(top_buckets.items(), key=lambda kv: -kv[1]):
    print(f'  {name:30s} {n / 1e6:8.1f} M')

# ---- Freeze every param NOT inside language_model.* ----
#
# Allowlist approach: only the text decoder is allowed to be
# (potentially) trainable. Vision tower, audio tower, multimodal
# projector, PLE bank, embed_*, lm_head and friends all get pinned
# regardless of how Gemma-4 names them internally.
TRAINABLE_PREFIX = 'language_model.'

n_frozen = n_passthrough = 0
for name, p in model.named_parameters():
    if not name.startswith(TRAINABLE_PREFIX):
        p.requires_grad = False
        n_frozen += p.numel()
    else:
        n_passthrough += p.numel()      # may still be LoRA-frozen below

print()
print(f'Frozen (non-text submodules)        : {n_frozen / 1e6:7.1f} M params')
print(f'Pre-LoRA trainable (text decoder)   : {n_passthrough / 1e6:7.1f} M params')
print(f'Total                                : {(n_frozen + n_passthrough) / 1e9:6.2f} B params')
"""


# ─────────────────────────────────────────────────────────────
# Section 5 — CCP dataset loader
# ─────────────────────────────────────────────────────────────
MD_CCP = """\
---

## 5. Build training records from CCP-DatasetNinja

Decode Supervise.ly bitmap masks → enclosing pixel bbox → DressApp
category → normalised 0..1000 grid. Produces `(image_path,
target_json_str, source_tag)` tuples.
"""

CODE_CCP_LOADER = """\
import base64, io, json, zlib, hashlib
import numpy as np
from PIL import Image

CCP_TO_CATEGORY = {
    # Tops
    'blouse':'Top','shirt':'Top','sweater':'Top','t-shirt':'Top','tee':'Top',
    'tank':'Top','top':'Top','vest':'Top',
    # Bottoms
    'pants':'Bottom','skirt':'Bottom','jeans':'Bottom','leggings':'Bottom','shorts':'Bottom',
    # Outerwear
    'coat':'Outerwear','jacket':'Outerwear','cape':'Outerwear','blazer':'Outerwear',
    # Full-body
    'dress':'Full-body','romper':'Full-body','suit':'Full-body',
    # Footwear
    'shoes':'Footwear','boots':'Footwear','heels':'Footwear','pumps':'Footwear',
    'sandals':'Footwear','wedges':'Footwear','socks':'Footwear','stockings':'Footwear',
    # Accessories
    'bag':'Accessory','purse':'Accessory','wallet':'Accessory','belt':'Accessory',
    'necklace':'Accessory','hat':'Accessory','sunglasses':'Accessory','glasses':'Accessory',
    'accessories':'Accessory','scarf':'Accessory','tie':'Accessory','gloves':'Accessory',
}
EXCLUDE = {'skin', 'hair', 'null', ''}


def _find_dataset_root(base):
    for path in base.rglob('img'):
        if path.is_dir() and (path.parent / 'ann').is_dir():
            return path.parent
    raise FileNotFoundError(f'No img/ + ann/ pair under {base}')


def _decode_mask_bbox(bitmap_obj):
    raw = base64.b64decode(bitmap_obj['data'])
    try:
        inner = zlib.decompress(raw)
    except zlib.error:
        inner = raw
    arr = np.array(Image.open(io.BytesIO(inner)))
    if arr.ndim == 3:
        arr = arr.max(axis=2)
    ys, xs = np.nonzero(arr)
    if ys.size == 0:
        return None
    ox, oy = bitmap_obj['origin']
    return (int(ox + xs.min()), int(oy + ys.min()),
            int(ox + xs.max()), int(oy + ys.max()))


def _norm_bbox(x1, y1, x2, y2, w, h):
    return [int(round(y1 / h * 1000)), int(round(x1 / w * 1000)),
            int(round(y2 / h * 1000)), int(round(x2 / w * 1000))]


def load_ccp_records():
    root = _find_dataset_root(CCP_DIR)
    records = []
    for jpg in sorted((root / 'img').glob('*.jpg')):
        ann_path = root / 'ann' / f'{jpg.name}.json'
        if not ann_path.exists():
            continue
        ann = json.loads(ann_path.read_text())
        w = int(ann.get('size', {}).get('width') or 0)
        h = int(ann.get('size', {}).get('height') or 0)
        if not (w and h):
            with Image.open(jpg) as im:
                w, h = im.size
        items = []
        for obj in ann.get('objects', []):
            cls = (obj.get('classTitle') or '').lower().strip()
            if cls in EXCLUDE or cls not in CCP_TO_CATEGORY:
                continue
            if obj.get('geometryType') != 'bitmap':
                continue
            bb = _decode_mask_bbox(obj['bitmap'])
            if bb is None:
                continue
            items.append({
                'label': cls,
                'category': CCP_TO_CATEGORY[cls],
                'region': {'bbox': _norm_bbox(*bb, w, h)},
            })
        if items:
            target = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
            records.append((str(jpg), target, 'ccp'))
    return records


ccp_records = load_ccp_records()
print(f'CCP records (>=1 garment): {len(ccp_records)}')
print('sample:', ccp_records[0][1][:300])
"""


# ─────────────────────────────────────────────────────────────
# Section 6 — DeepFashion loader
# ─────────────────────────────────────────────────────────────
MD_DF = """\
---

## 6. Build training records from DeepFashion-Multimodal

DeepFashion-Multimodal ships with image+attribute pairs and (for the
Kaggle copy `silverstone1903/deep-fashion-multimodal`) per-image
bounding boxes for the visible garment(s). The loader is defensive:

1. Walks the unzipped dataset directory.
2. Identifies the annotation file (CSV / JSON / TXT — Kaggle copies
   vary).
3. Falls back to whole-frame bboxes if nothing parses, rather than
   skipping the dataset outright.

If the dataset layout in your downloaded copy differs (e.g. nested
inside a `dfmm/` folder), the **first cell** below prints what was
found — adjust the loader path in the second cell if needed.
"""

CODE_DF_INSPECT = """\
import pathlib, os

# Print the top of the DeepFashion folder so we know the layout.
for root, dirs, files in os.walk(DF_DIR):
    rel = pathlib.Path(root).relative_to(DF_DIR.parent)
    print(rel, '  ->  ', len(files), 'files')
    for f in sorted(files)[:5]:
        print('   ', f)
    if len(dirs) > 5:
        print('   ', len(dirs), 'subdirs (first 5 walked)')
    # don't descend too deep
    if len(str(rel).split(os.sep)) > 2:
        dirs.clear()
"""

CODE_DF_LOADER = """\
# Adjust paths here if the inspect cell above shows a different layout.
#
# Typical silverstone1903/deep-fashion-multimodal layout:
#   deepfashion_mm/
#       images/                       (.jpg, ~12k)
#       train.txt | annotations.csv   (per-image attribute / bbox table)
#
# The loader below is permissive: it tries a few common paths and
# common annotation column schemas, and skips images it can't parse.

import csv, json
from PIL import Image

DF_TO_CATEGORY = {
    'sleeveless_dress':'Full-body', 'short_sleeve_dress':'Full-body',
    'long_sleeve_dress':'Full-body', 'vest_dress':'Full-body',
    'sling_dress':'Full-body', 'dress':'Full-body',
    'short_sleeve_top':'Top', 'long_sleeve_top':'Top',
    'sleeveless_top':'Top', 'top':'Top', 'tee':'Top', 'shirt':'Top',
    'short_sleeve_outwear':'Outerwear', 'long_sleeve_outwear':'Outerwear',
    'outwear':'Outerwear', 'coat':'Outerwear', 'jacket':'Outerwear',
    'shorts':'Bottom', 'trousers':'Bottom', 'pants':'Bottom',
    'skirt':'Bottom', 'jeans':'Bottom',
    'vest':'Top', 'sling':'Top',
}

def _find_df_image_dir():
    for candidate in ('images', 'img', 'image'):
        p = DF_DIR / candidate
        if p.is_dir():
            return p
    # Fallback - first sub-dir with a lot of jpgs
    for sub in DF_DIR.iterdir():
        if sub.is_dir() and len(list(sub.glob('*.jpg'))) > 100:
            return sub
    raise FileNotFoundError(f'No image directory under {DF_DIR}')


def _find_df_annotations():
    # Look for CSV, then JSON, then TXT.
    for pattern in ('**/*.csv', '**/*.json', '**/*.txt'):
        for p in DF_DIR.rglob(pattern):
            if p.stat().st_size < 100:
                continue
            return p
    return None


def load_deepfashion_records():
    img_dir = _find_df_image_dir()
    ann_path = _find_df_annotations()
    print(f'DeepFashion images dir : {img_dir}')
    print(f'DeepFashion annot file : {ann_path}')

    records = []
    if ann_path is None:
        print('No annotation file found; skipping DeepFashion.')
        return records

    # Strategy A - CSV with columns like image_name,category,x1,y1,x2,y2
    if ann_path.suffix == '.csv':
        rows = list(csv.DictReader(open(ann_path)))
        for row in rows:
            keys_lower = {k.lower(): v for k, v in row.items()}
            img_name = keys_lower.get('image_name') or keys_lower.get('image') or keys_lower.get('filename')
            if not img_name:
                continue
            img_path = img_dir / img_name
            if not img_path.exists():
                continue
            cat_raw = (keys_lower.get('category') or keys_lower.get('class') or '').lower().strip()
            cat = DF_TO_CATEGORY.get(cat_raw, 'Top')
            try:
                x1 = int(keys_lower.get('x1') or keys_lower.get('xmin') or 0)
                y1 = int(keys_lower.get('y1') or keys_lower.get('ymin') or 0)
                x2 = int(keys_lower.get('x2') or keys_lower.get('xmax') or 0)
                y2 = int(keys_lower.get('y2') or keys_lower.get('ymax') or 0)
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            with Image.open(img_path) as im:
                w, h = im.size
            items = [{
                'label': cat_raw or 'garment',
                'category': cat,
                'region': {'bbox': _norm_bbox(x1, y1, x2, y2, w, h)},
            }]
            target = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
            records.append((str(img_path), target, 'deepfashion'))
        return records

    # Strategy B - JSON list of dicts
    if ann_path.suffix == '.json':
        try:
            data = json.load(open(ann_path))
            if isinstance(data, dict) and 'annotations' in data:
                data = data['annotations']
            for row in data:
                img_name = (row.get('image_name') or row.get('file_name')
                            or row.get('image') or row.get('img'))
                if not img_name:
                    continue
                img_path = img_dir / img_name
                if not img_path.exists():
                    continue
                cat_raw = (row.get('category') or row.get('class') or '').lower().strip()
                cat = DF_TO_CATEGORY.get(cat_raw, 'Top')
                bbox = row.get('bbox') or row.get('box')
                if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                if x2 <= x1 or y2 <= y1:
                    continue
                with Image.open(img_path) as im:
                    w, h = im.size
                items = [{
                    'label': cat_raw or 'garment',
                    'category': cat,
                    'region': {'bbox': _norm_bbox(x1, y1, x2, y2, w, h)},
                }]
                records.append((str(img_path),
                                json.dumps(items, ensure_ascii=False, separators=(',', ':')),
                                'deepfashion'))
            return records
        except Exception as e:
            print(f'JSON parse failed: {e}')
            return records

    # Strategy C - fallback: enumerate images with whole-frame bboxes.
    print('Annotation format not recognised; falling back to whole-frame bboxes.')
    for img_path in sorted(img_dir.glob('*.jpg'))[:5000]:
        with Image.open(img_path) as im:
            w, h = im.size
        items = [{
            'label': 'garment',
            'category': 'Top',
            'region': {'bbox': [0, 0, 1000, 1000]},
        }]
        records.append((str(img_path),
                        json.dumps(items, ensure_ascii=False, separators=(',', ':')),
                        'deepfashion'))
    return records


df_records = load_deepfashion_records()
print(f'DeepFashion records: {len(df_records)}')
if df_records:
    print('sample:', df_records[0][1][:300])
"""


# ─────────────────────────────────────────────────────────────
# Section 7 — Combine + deterministic split
# ─────────────────────────────────────────────────────────────
MD_SPLIT = """\
---

## 7. Combine datasets and split

Stratified 80/10/10 split — the train/val/test ratio is held inside
each source (CCP and DeepFashion) so val + test always contain a mix.
"""

CODE_SPLIT = """\
def _bucket(path):
    h = int(hashlib.sha256(path.encode()).hexdigest(), 16) % 100
    if h < 80: return 'train'
    if h < 90: return 'val'
    return 'test'

train, val, test = [], [], []
for rec in ccp_records + df_records:
    {'train': train, 'val': val, 'test': test}[_bucket(rec[0])].append(rec)

print(f'Combined: train={len(train)}  val={len(val)}  test={len(test)}')

by_src = {}
for rec in train:
    by_src[rec[2]] = by_src.get(rec[2], 0) + 1
print('Train mix:', by_src)
"""


# ─────────────────────────────────────────────────────────────
# Section 8 — Conversation builder + collator
# ─────────────────────────────────────────────────────────────
MD_CONV = """\
---

## 8. Conversation builder + masked-loss collator

Four things this section gets right per the dev.to Gemma-4 guide
and the HF model card:

1. **Roles are `system` / `user` / `assistant`**, the native Gemma-4
   convention — *not* the Gemma-3 `model` role. The HF model card
   explicitly notes: "Compared to Gemma 3, the models use standard
   `system`, `assistant`, and `user` roles."
2. **`enable_thinking=False`** is set on the chat template. Gemma-4
   has a built-in `<|think|>` reasoning mode that we explicitly
   disable for Eyes — we want a clean JSON array as the only output,
   not a reasoning trace. (We also make sure SYSTEM_PROMPT does NOT
   start with the `<|think|>` token, which is the alternate way
   thinking gets enabled.)
3. **Images come BEFORE text** inside the user message content
   array, per the model-card best practice.
4. **Content is a list-of-parts** for every role
   (`[{"type": "text", "text": "..."}]`), matching the dev.to
   examples. The processor reads the PIL image directly from
   `{"type": "image", "image": <PIL>}` inline — no separate
   `images=` kwarg.

The collator then masks out user-side tokens with `ignore_index=-100`
so gradient flows ONLY through the JSON the model is supposed to
emit (the assistant turn).
"""

CODE_PROMPT = """\
SYSTEM_PROMPT = (
    'You are DressApp Eyes, a vision model specialised in clothing.\\n'
    'You receive ONE photograph and return ONLY valid JSON.\\n\\n'
    'Schema: a JSON array. Each element describes ONE distinct visible\\n'
    'garment, accessory, or footwear item:\\n'
    '  { \"label\":    string,\\n'
    '    \"category\": one of [Top|Bottom|Outerwear|Full-body|Footwear|Accessory],\\n'
    '    \"region\":   { \"bbox\": [ymin, xmin, ymax, xmax] }  // 0..1000 grid\\n'
    '  }\\n\\n'
    'Rules:\\n'
    ' - Always return an array. A single-garment photo returns a one-element array.\\n'
    ' - List EVERY distinct garment. Layered outfits = N elements.\\n'
    ' - Skip skin, hair, body parts, backgrounds.\\n'
    ' - bbox values are integers on a 0..1000 grid, NOT pixels.\\n'
    ' - No prose, no markdown - JSON only.\\n'
)
USER_INSTRUCTION = 'Analyze this outfit photograph and return the JSON array.'

# Sanity: SYSTEM_PROMPT MUST NOT start with <|think|>, which would
# enable Gemma-4's chain-of-thought reasoning trace.
assert not SYSTEM_PROMPT.lstrip().startswith('<|think|>'), \\
    'Remove the <|think|> token from SYSTEM_PROMPT - Eyes emits JSON only.'

print(SYSTEM_PROMPT[:200], '...')
"""

CODE_BUILD_EXAMPLE = """\
import torch
from PIL import Image as _PIL_Image

def build_example(record, *, ignore_index=-100):
    img_path, target_json, _source = record
    image = _PIL_Image.open(img_path).convert('RGB')

    # Gemma-4 chat format: native system/user/assistant roles, every
    # content is a list of typed parts, image goes BEFORE text in
    # the user turn, image is inline (no images= kwarg needed).
    messages_full = [
        {'role': 'system', 'content': [{'type': 'text', 'text': SYSTEM_PROMPT}]},
        {'role': 'user',   'content': [
            {'type': 'image', 'image': image},
            {'type': 'text',  'text':  USER_INSTRUCTION},
        ]},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': target_json}]},
    ]
    messages_prompt = messages_full[:2]

    # Disable thinking via the template flag (belt-and-braces with the
    # assert above on SYSTEM_PROMPT).
    full = processor.apply_chat_template(
        messages_full,
        add_generation_prompt=False,
        tokenize=True,
        return_dict=True,
        return_tensors='pt',
        enable_thinking=False,
    )
    prompt = processor.apply_chat_template(
        messages_prompt,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors='pt',
        enable_thinking=False,
    )

    input_ids = full['input_ids'][0]
    labels    = input_ids.clone()
    n_prompt  = prompt['input_ids'].shape[1]
    labels[:n_prompt] = ignore_index

    out = {
        'input_ids':      input_ids,
        'attention_mask': full['attention_mask'][0],
        'labels':         labels,
        'pixel_values':   full['pixel_values'][0],
    }
    if 'token_type_ids' in full:
        out['token_type_ids'] = full['token_type_ids'][0]
    return out


ex = build_example(train[0])
for k, v in ex.items():
    print(f'  {k:16s} shape={tuple(v.shape)} dtype={v.dtype}')
print(f'  loss-active tokens : {(ex[\"labels\"] != -100).sum().item()}')
"""

CODE_COLLATOR = """\
from dataclasses import dataclass

@dataclass
class GemmaVLCollator:
    pad_token_id: int
    ignore_index: int = -100

    def __call__(self, batch):
        max_len = max(len(b['input_ids']) for b in batch)
        out = {'input_ids':[], 'attention_mask':[], 'labels':[], 'pixel_values':[]}
        for b in batch:
            n_pad = max_len - len(b['input_ids'])
            out['input_ids'].append(
                torch.cat([b['input_ids'],
                           torch.full((n_pad,), self.pad_token_id, dtype=b['input_ids'].dtype)]))
            out['attention_mask'].append(
                torch.cat([b['attention_mask'],
                           torch.zeros(n_pad, dtype=b['attention_mask'].dtype)]))
            out['labels'].append(
                torch.cat([b['labels'],
                           torch.full((n_pad,), self.ignore_index, dtype=b['labels'].dtype)]))
            out['pixel_values'].append(b['pixel_values'])
        return {
            'input_ids':      torch.stack(out['input_ids']),
            'attention_mask': torch.stack(out['attention_mask']),
            'labels':         torch.stack(out['labels']),
            'pixel_values':   torch.stack(out['pixel_values']),
        }

collator = GemmaVLCollator(pad_token_id=processor.tokenizer.pad_token_id)
print('collator ready. pad_id =', collator.pad_token_id)
"""

CODE_DATASET_CLASS = """\
from torch.utils.data import Dataset

class RecordDataset(Dataset):
    def __init__(self, recs): self.recs = recs
    def __len__(self):  return len(self.recs)
    def __getitem__(self, i): return build_example(self.recs[i])

train_ds = RecordDataset(train)
val_ds   = RecordDataset(val)
test_ds  = RecordDataset(test)
print(f'train {len(train_ds)}   val {len(val_ds)}   test {len(test_ds)}')
"""


# ─────────────────────────────────────────────────────────────
# Section 9 — LoRA
# ─────────────────────────────────────────────────────────────
MD_LORA = """\
---

## 9. LoRA (text decoder only)

Standard rank-16 / alpha-32 LoRA on the text decoder's
`q/k/v/o/gate/up/down_proj` linears. PEFT auto-discovers them by
suffix match — the discovery is restricted to the parameters that
*could* be trainable at this point, which is exactly
`language_model.*` (everything else was hard-frozen in section 4).
The `model.print_trainable_parameters()` call right after should
print something like "0.6 % trainable" — sanity-check that figure
before kicking off training.
"""

CODE_LORA = """\
from peft import LoraConfig, get_peft_model, TaskType

lora_cfg = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias='none',
    task_type=TaskType.CAUSAL_LM,
    target_modules=[
        'q_proj','k_proj','v_proj','o_proj',
        'gate_proj','up_proj','down_proj',
    ],
)

model = get_peft_model(model, lora_cfg)
model.print_trainable_parameters()           # expect < 1 %
"""


# ─────────────────────────────────────────────────────────────
# Section 10 — Train
# ─────────────────────────────────────────────────────────────
MD_TRAIN = """\
---

## 10. Train

A100 + bf16 -> no QLoRA. Batch 2 x grad-accum 8 = effective 16.
~14 k records / 16 ~= 875 steps/epoch x 2 epochs = ~1750 total
steps. Checkpoint to Drive every 200 steps for disconnect insurance.
"""

CODE_TRAIN_ARGS = """\
from transformers import TrainingArguments, Trainer

args = TrainingArguments(
    output_dir=str(OUT_RUN),
    overwrite_output_dir=True,
    num_train_epochs=2,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,            # effective batch 16
    per_device_eval_batch_size=2,
    bf16=True,
    gradient_checkpointing=True,
    optim='adamw_torch_fused',
    learning_rate=2e-4,
    lr_scheduler_type='cosine',
    warmup_ratio=0.03,
    weight_decay=0.01,
    max_grad_norm=1.0,
    logging_steps=20,
    save_strategy='steps',
    save_steps=200,
    save_total_limit=3,
    eval_strategy='steps',
    eval_steps=200,
    load_best_model_at_end=True,
    metric_for_best_model='eval_loss',
    greater_is_better=False,
    report_to='none',
    remove_unused_columns=False,
    dataloader_num_workers=2,
    dataloader_pin_memory=True,
    seed=42,
)
print('args configured.')
"""

CODE_TRAIN_RUN = """\
trainer = Trainer(
    model=model,
    args=args,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    data_collator=collator,
)
trainer.train()
"""


# ─────────────────────────────────────────────────────────────
# Section 11 — Quick eval (bbox IoU)
# ─────────────────────────────────────────────────────────────
MD_EVAL = """\
---

## 11. Quick bbox-IoU eval on held-out test split

Same metric as `/app/scripts/run_eyes_benchmark.py` so v4 numbers
are directly comparable to the v3 (Gemini-Flash) and SegFormer +
per-crop benches we recorded earlier:

| Pipeline | mean IoU | recall@0.5 | precision@0.5 |
| --- | ---: | ---: | ---: |
| v3 one-pass (Gemini-Flash) | 0.49 | 0.10 | 0.53 |
| SegFormer + per-crop Eyes | 0.74 | 0.56 | 0.78 |
| **v4 fine-tuned one-pass** | ? | ? | ? |
"""

CODE_EVAL = """\
import re, time, json
import numpy as np

model.eval()

def _safe_parse(s):
    m = re.search(r'\\[.*\\]', s, flags=re.DOTALL)
    if not m: return None
    try:    return json.loads(m.group(0))
    except: return None

def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if not inter: return 0.0
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union else 0.0

def _denorm(bb, w, h):
    ymin, xmin, ymax, xmax = bb
    return (int(xmin/1000*w), int(ymin/1000*h), int(xmax/1000*w), int(ymax/1000*h))

def _predict(img_path):
    image = _PIL_Image.open(img_path).convert('RGB')
    msgs = [
        {'role':'system','content':[{'type':'text','text':SYSTEM_PROMPT}]},
        {'role':'user',  'content':[
            {'type':'image','image':image},
            {'type':'text', 'text':USER_INSTRUCTION},
        ]},
    ]
    enc = processor.apply_chat_template(
        msgs,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors='pt',
        enable_thinking=False,
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=512,
            do_sample=False,
            pad_token_id=processor.tokenizer.pad_token_id,
        )
    return _safe_parse(
        processor.tokenizer.decode(out[0][enc['input_ids'].shape[1]:],
                                   skip_special_tokens=True))

ious, n_gt, n_pred, n_match = [], 0, 0, 0
t0 = time.perf_counter()
for img_path, target_json, _src in test_ds.recs:
    gts = json.loads(target_json)
    with _PIL_Image.open(img_path) as im: w, h = im.size
    gts_px = [_denorm(g['region']['bbox'], w, h) for g in gts]
    preds = _predict(img_path)
    if not isinstance(preds, list):
        n_gt += len(gts_px); continue
    preds_px = []
    for p in preds:
        bb = (p.get('region') or {}).get('bbox')
        if isinstance(bb, list) and len(bb) == 4:
            preds_px.append(_denorm(bb, w, h))
    triples = sorted(
        [(_iou(p, g), pi, gi)
         for pi, p in enumerate(preds_px)
         for gi, g in enumerate(gts_px)],
        reverse=True)
    up, ug = set(), set()
    for iou, pi, gi in triples:
        if pi in up or gi in ug: continue
        up.add(pi); ug.add(gi); ious.append(iou)
        if iou >= 0.5: n_match += 1
    n_gt += len(gts_px); n_pred += len(preds_px)

el = time.perf_counter() - t0
print(f'tested {len(test_ds.recs)} in {el:.1f}s')
print(f'  mean IoU            : {np.mean(ious):.3f}' if ious else '  no preds')
print(f'  recall @ IoU=0.5    : {n_match/n_gt:.3f}' if n_gt else '')
print(f'  precision @ IoU=0.5 : {n_match/n_pred:.3f}' if n_pred else '')
print(f'  avg preds / image   : {n_pred/len(test_ds.recs):.2f}')
"""


# ─────────────────────────────────────────────────────────────
# Section 12 — Merge LoRA + save bf16
# ─────────────────────────────────────────────────────────────
MD_MERGE = """\
---

## 12. Merge LoRA + save bf16 to Drive

`merge_and_unload()` folds the rank-16 adapter matrices back into
the base linear layers, so the resulting checkpoint is a vanilla
Gemma-4 multimodal model that any downstream tool (llama.cpp, vLLM,
HF Transformers, etc.) can load without PEFT in the picture.
"""

CODE_MERGE = """\
merged = model.merge_and_unload()
OUT_MERGED.mkdir(parents=True, exist_ok=True)
merged.save_pretrained(str(OUT_MERGED),
                       safe_serialization=True,
                       max_shard_size='4GB')
processor.save_pretrained(str(OUT_MERGED))

total_gb = sum(p.stat().st_size for p in OUT_MERGED.rglob('*')) / (1024**3)
print(f'Saved merged bf16 to {OUT_MERGED} ({total_gb:.2f} GB)')
"""


# ─────────────────────────────────────────────────────────────
# Section 13 — Quantize to GGUF (text + mmproj)
# ─────────────────────────────────────────────────────────────
MD_QUANT = """\
---

## 13. Convert to GGUF + quantize to Q4_K_M

Two artifacts get produced:

1. **Text-model GGUF** (Q4_K_M, ~3 GB) — the language decoder + token
   embeddings, what the Hetzner llama-server actually runs.
2. **Vision projector GGUF** (fp16, ~1 GB) — the SigLIP-style vision
   tower + multimodal projector from `gemma-4-E2B-it`.

### Known caveats (Gemma-4 + llama.cpp, as of May 2026)

* Gemma-4 **text + image inference is stable** on llama.cpp `master`.
* Gemma-4 **audio support is still WIP** in llama.cpp — we don't
  need audio for Eyes, so we skip it cleanly.
* `convert_hf_to_gguf.py` has a known `KeyError: 'image_mean'` when
  exporting the multimodal projector on some Gemma-4 checkpoints
  (llama.cpp issue #21775). The mmproj cell below patches the
  preprocessor config in-place if the key is missing, then retries.

We build llama.cpp from `master` (not a pinned tag) to pick up the
latest Gemma-4 PRs.
"""

CODE_GGUF_BUILD = """\
%cd /content
![ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp llama.cpp
%cd /content/llama.cpp
!git pull --ff-only 2>&1 | tail -3
!pip install -q -r requirements/requirements-convert_hf_to_gguf.txt
!cmake -B build -DGGML_CUDA=ON 2>&1 | tail -3
!cmake --build build --config Release --target llama-quantize -j 2>&1 | tail -3
"""

CODE_GGUF_TEXT = """\
F16_GGUF = OUT_RUN / 'Eyes_v4_Gemma4-f16.gguf'

# Convert the text decoder to GGUF in fp16.
!python /content/llama.cpp/convert_hf_to_gguf.py \\
    {OUT_MERGED} \\
    --outtype f16 \\
    --outfile {F16_GGUF}

print('fp16 text GGUF size:', round(F16_GGUF.stat().st_size / 1024**3, 2), 'GB')
"""

CODE_GGUF_MMPROJ = """\
# Convert the vision tower + multimodal projector to its own GGUF.
#
# Workaround for llama.cpp issue #21775: convert_hf_to_gguf.py
# crashes with KeyError: 'image_mean' when the merged checkpoint's
# preprocessor_config.json is missing certain HF defaults. If that
# happens, we patch the config and retry once.
import json, subprocess, pathlib

pp_cfg = pathlib.Path(OUT_MERGED) / 'preprocessor_config.json'
if pp_cfg.exists():
    cfg = json.loads(pp_cfg.read_text())
    patched = False
    if 'image_mean' not in cfg:
        cfg['image_mean'] = [0.5, 0.5, 0.5]; patched = True
    if 'image_std' not in cfg:
        cfg['image_std']  = [0.5, 0.5, 0.5]; patched = True
    if patched:
        pp_cfg.write_text(json.dumps(cfg, indent=2))
        print('Patched preprocessor_config.json with default image_mean/std.')

cmd = [
    'python', '/content/llama.cpp/convert_hf_to_gguf.py',
    str(OUT_MERGED),
    '--mmproj',
    '--outtype', 'f16',
    '--outfile', str(OUT_MMPROJ),
]
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout[-2000:])
if r.returncode != 0:
    print('STDERR:', r.stderr[-2000:])
    raise RuntimeError(
        'mmproj conversion failed. If the error mentions an '
        'unsupported architecture, rebuild llama.cpp from master '
        '(git pull, cmake --build) and retry this cell. See '
        'https://github.com/ggml-org/llama.cpp/issues/21775 for context.'
    )

print('mmproj fp16 size:', round(OUT_MMPROJ.stat().st_size / 1024**3, 2), 'GB')
"""

CODE_GGUF_QUANT = """\
# Quantize the TEXT model only (mmproj stays fp16 - image-tower
# quantization is finicky and the projector is small anyway).
!/content/llama.cpp/build/bin/llama-quantize \\
    {F16_GGUF} \\
    {OUT_GGUF} \\
    Q4_K_M

print('text Q4_K_M size:', round(OUT_GGUF.stat().st_size / 1024**3, 2), 'GB')
print()
print('=== v4 artifacts on Drive ===')
print(' ', OUT_GGUF)
print(' ', OUT_MMPROJ)
"""


# ─────────────────────────────────────────────────────────────
# Section 14 — Sanity probe
# ─────────────────────────────────────────────────────────────
MD_PROBE = """\
---

## 14. Sanity probe — load the new GGUFs via llama-cpp-python

Confirms the new artifact pair loads together, emits valid JSON,
and returns multi-element arrays on multi-garment photos. If THIS
works, the Hetzner deploy will too.

If `llama-cpp-python` doesn't yet ship a `Gemma4ChatHandler`, the
generic `Llava15ChatHandler` is a compatible fallback for vision +
text on Gemma-family multimodal GGUFs.

> **Optional second smoke-test via Ollama.** The Ollama project
> ships an official Q4_K_M build of stock Gemma-4 E2B as
> `gemma4:e2b`. After Eyes v4 is exported, you can sanity-check the
> base prompt template by running `ollama run gemma4:e2b` against
> the same photos and comparing the response shape. Our Q4_K_M
> tensor formats and tokenizer match Ollama's, so any divergence
> means the merge step corrupted something.
"""

CODE_PROBE_INSTALL = """\
%pip install -q --upgrade \\
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 \\
    'llama-cpp-python'
"""

CODE_PROBE_RUN = """\
import random, json
from llama_cpp import Llama

try:
    from llama_cpp.llama_chat_format import Gemma4ChatHandler as VisionHandler
    print('Using Gemma4ChatHandler.')
except ImportError:
    from llama_cpp.llama_chat_format import Llava15ChatHandler as VisionHandler
    print('Gemma4ChatHandler not in this llama-cpp-python build; '
          'falling back to Llava15ChatHandler.')

handler = VisionHandler(clip_model_path=str(OUT_MMPROJ))
llm = Llama(
    model_path=str(OUT_GGUF),
    chat_handler=handler,
    n_ctx=4096,
    n_gpu_layers=-1,
    verbose=False,
)

random.seed(42)
samples = random.sample(test_ds.recs, k=min(5, len(test_ds.recs)))

for img_path, target_json, src in samples:
    print('=' * 70)
    print(f'Image  : {pathlib.Path(img_path).name}  (source: {src})')
    resp = llm.create_chat_completion(
        messages=[
            {'role':'system','content':[{'type':'text','text':SYSTEM_PROMPT}]},
            {'role':'user','content':[
                {'type':'image_url','image_url':{'url': f'file://{img_path}'}},
                {'type':'text','text': USER_INSTRUCTION},
            ]},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp['choices'][0]['message']['content']
    parsed = _safe_parse(raw)
    print('Predicted :', json.dumps(parsed, indent=2)[:600]
          if parsed else f'(unparseable) raw={raw[:200]}')
    print('Truth     :', json.dumps(json.loads(target_json), indent=2)[:600])
"""


# ─────────────────────────────────────────────────────────────
# Section 15 — Done / hand-off
# ─────────────────────────────────────────────────────────────
MD_DONE = """\
---

## Done — Hetzner deploy hand-off

Both GGUF artifacts ship together:

```bash
# on the Hetzner box, replace the running v2/v3 pair with the new v4 pair
scp Eyes_v4_Gemma4-Q4_K_M.gguf      hetzner:/srv/eyes/models/
scp mmproj-Eyes_v4_Gemma4-f16.gguf  hetzner:/srv/eyes/models/

# update the llama-server invocation to point to the new files:
#   --model      /srv/eyes/models/Eyes_v4_Gemma4-Q4_K_M.gguf
#   --mmproj     /srv/eyes/models/mmproj-Eyes_v4_Gemma4-f16.gguf
docker compose restart eyes
```

Then re-run the in-pod benchmark from the chat thread to validate
the gate end-to-end through the FastAPI bridge:

```bash
/root/.venv/bin/python /app/scripts/run_eyes_benchmark.py \\
    --analyzer=one_pass --limit=30
```

If `recall@0.5 >= 0.8` holds and `mean IoU >= 0.6`, you can un-retire
`EYES_ONE_PASS=true` in production and ship the simpler one-call
path back into the closet analyze flow.
"""


# ─────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────
CELLS = [
    md(MD_TITLE),
    md(MD_DRIVE),  code(CODE_MOUNT), code(CODE_GPU), code(CODE_PATHS),
    md(MD_DEPS),   code(CODE_DEPS),
    md(MD_AUTH),   code(CODE_HF_AUTH), code(CODE_KAGGLE_AUTH), code(CODE_DF_DOWNLOAD),
    md(MD_LOAD),   code(CODE_LOAD),
    md(MD_CCP),    code(CODE_CCP_LOADER),
    md(MD_DF),     code(CODE_DF_INSPECT), code(CODE_DF_LOADER),
    md(MD_SPLIT),  code(CODE_SPLIT),
    md(MD_CONV),   code(CODE_PROMPT), code(CODE_BUILD_EXAMPLE),
                   code(CODE_COLLATOR), code(CODE_DATASET_CLASS),
    md(MD_LORA),   code(CODE_LORA),
    md(MD_TRAIN),  code(CODE_TRAIN_ARGS), code(CODE_TRAIN_RUN),
    md(MD_EVAL),   code(CODE_EVAL),
    md(MD_MERGE),  code(CODE_MERGE),
    md(MD_QUANT),  code(CODE_GGUF_BUILD), code(CODE_GGUF_TEXT),
                   code(CODE_GGUF_MMPROJ), code(CODE_GGUF_QUANT),
    md(MD_PROBE),  code(CODE_PROBE_INSTALL), code(CODE_PROBE_RUN),
    md(MD_DONE),
]

NB = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {"display_name": "Python 3 (Colab)",
                       "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
        "accelerator": "GPU",
        "colab": {"gpuClass": "premium", "provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(NB, indent=1) + "\n")
print(f"Wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB, {len(CELLS)} cells)")
