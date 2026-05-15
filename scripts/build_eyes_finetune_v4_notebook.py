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
> **Authoritative loading recipe** (from the HF model card):
> ```python
> from transformers import AutoProcessor, AutoModelForMultimodalLM
> processor = AutoProcessor.from_pretrained("google/gemma-4-E2B-it")
> model = AutoModelForMultimodalLM.from_pretrained(
>     "google/gemma-4-E2B-it", dtype="auto", device_map="auto")
> ```
> We use `AutoModelForMultimodalLM` (full text+image+audio head)
> rather than the narrower `AutoModelForImageTextToText` used in the
> dev.to QLoRA blog post. Eyes is image-only **for this LoRA run**,
> but the *next* training phase will exercise audio input (ASR /
> speech-to-translated-text for in-app voice queries about an
> outfit), so we load the full multimodal head now to avoid having
> to re-export and re-quantize the model from a different base
> checkpoint later. The audio tower is hard-frozen during this run;
> the next-phase LoRA will simply unfreeze it.
> No hand-rolled `Gemma4*ForConditionalGeneration` import — the Auto
> classes dispatch to whatever the installed transformers release
> ships as the multimodal head for Gemma-4. Requires
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
from transformers import AutoModelForMultimodalLM  # noqa: F401
print('AutoModelForMultimodalLM import : OK')

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
# Marqo/deepfashion-multimodal (HF Hub) — replaces the broken Kaggle
# silverstone1903/deep-fashion-multimodal source. 42,537 rows, single
# 'data' split. NO bounding boxes — only rich multi-garment captions
# and a coarse category2 label. We parse the captions into per-garment
# mentions with whole-frame bboxes. CCP-DatasetNinja still provides
# the precise bbox supervision; Marqo adds scale + multi-garment-
# per-image count discipline.
#
# This cell populates df_records DIRECTLY, so Section 6 (the on-disk
# annotation file scanner) is obsolete and should be skipped.
%pip install -q -U 'datasets>=4.0.0'

import re, json
from datasets import load_dataset

# Auth was already done in Section 3 (HF_TOKEN from Colab Secrets).
ds = load_dataset('Marqo/deepfashion-multimodal', split='data')
print(f'Marqo/deepfashion-multimodal: {len(ds):,} rows')
print('schema :', list(ds.features.keys()))

IMG_DIR = DF_DIR / 'images'
IMG_DIR.mkdir(parents=True, exist_ok=True)

# Caption parser — extracts per-garment mentions, maps each to a
# DressApp category. Order matters (Full-body wins over shirt/pants
# substrings). One item per category per image (deduped).
GARMENT_PATTERNS = [
    (r'\\b(dress|gown|romper|jumpsuit|onesie)\\b',                 'dress',     'Full-body'),
    (r'\\bouter clothing\\b',                                       'outerwear', 'Outerwear'),
    (r'\\b(jacket|coat|blazer|cardigan|cape|parka|trench)\\b',     None,        'Outerwear'),
    (r'\\b(t[-\\s]?shirt|tee)\\b',                                  't-shirt',   'Top'),
    (r'\\btank(?:\\s+(?:top|shirt))?\\b',                           'tank top',  'Top'),
    (r'\\b(blouse|shirt|sweater|hoodie|sweatshirt|polo|vest|top)\\b', None,      'Top'),
    (r'\\b(jeans|denim pants)\\b',                                  'jeans',     'Bottom'),
    (r'\\b(trousers|pants|shorts|leggings|skirt)\\b',               None,        'Bottom'),
    (r'\\b(hat|cap|beanie)\\b',                                     'hat',       'Accessory'),
    (r'\\b(sunglasses|glasses)\\b',                                 None,        'Accessory'),
    (r'\\b(bag|purse|wallet|backpack|handbag)\\b',                  'bag',       'Accessory'),
    (r'\\bbelt\\b',                                                 'belt',      'Accessory'),
    (r'\\b(scarf|tie|gloves|necklace|bracelet|ring|watch)\\b',      None,        'Accessory'),
    (r'accessory on his wrist',                                    'watch',     'Accessory'),
]
WHOLE_FRAME = [0, 0, 1000, 1000]   # ymin, xmin, ymax, xmax on 0..1000 grid

DF2_TO_CAT = {
    'denim':'Bottom', 'pants':'Bottom', 'shorts':'Bottom',
    'leggings':'Bottom', 'skirts':'Bottom',
    'tees_tanks':'Top', 'shirts_polos':'Top', 'sweaters':'Top',
    'blouses_shirts':'Top', 'cardigans':'Top', 'sweatshirts_hoodies':'Top',
    'jackets':'Outerwear', 'jackets_vests':'Outerwear', 'jackets_coats':'Outerwear',
    'dresses':'Full-body', 'rompers_jumpsuits':'Full-body', 'jumpsuits_rompers':'Full-body',
}

def parse_caption(text, category2):
    text_l = (text or '').lower()
    items, seen = [], set()
    for pat, default_label, cat in GARMENT_PATTERNS:
        m = re.search(pat, text_l)
        if not m or cat in seen:
            continue
        seen.add(cat)
        items.append({
            'label': default_label or m.group(0).strip(),
            'category': cat,
            'region': {'bbox': WHOLE_FRAME[:]},
        })
    if not items:
        cat = DF2_TO_CAT.get((category2 or '').lower(), 'Top')
        items.append({
            'label': category2 or 'garment',
            'category': cat,
            'region': {'bbox': WHOLE_FRAME[:]},
        })
    return items


df_records = []
for i, row in enumerate(ds):
    img_path = IMG_DIR / f'{row[\"item_ID\"]}.jpg'
    if not img_path.exists():
        row['image'].convert('RGB').save(img_path, 'JPEG', quality=92)
    items = parse_caption(row['text'], row.get('category2'))
    target = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    df_records.append((str(img_path), target, 'deepfashion'))
    if i and i % 5000 == 0:
        print(f'  materialized {i:>6,}/{len(ds):,}  df_records={len(df_records):,}')

(DF_DIR / '_done').touch()
print(f'\\nfinal df_records: {len(df_records):,}')
print('sample target :', df_records[0][1][:400])

from collections import Counter
n_per_img = Counter(len(json.loads(r[1])) for r in df_records)
print('items-per-image histogram:', dict(sorted(n_per_img.items())))
"""


# ─────────────────────────────────────────────────────────────
# Section 4 — Load Gemma-4 + freeze everything except text-decoder
# ─────────────────────────────────────────────────────────────
MD_LOAD = """\
---

## 4. Load `google/gemma-4-E2B-it` and aggressively freeze

We use `AutoModelForMultimodalLM` — the full text+image+audio head
— rather than the narrower `AutoModelForImageTextToText` used in
the dev.to QLoRA blog post. Eyes is image-only **for this LoRA
run**, but the next training phase will exercise the audio tower
(ASR / speech-to-translated-text for in-app voice queries about
an outfit), so we load the full multimodal head now to keep the
audio weights present and avoid having to re-export the merged
checkpoint from a different base later.

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
   ever sees a gradient. The audio tower stays frozen here; the
   next-phase audio LoRA will explicitly unfreeze it then.
"""

CODE_LOAD = """\
import torch
from collections import Counter
from transformers import AutoProcessor, AutoModelForMultimodalLM

BASE_MODEL = 'google/gemma-4-E2B-it'

processor = AutoProcessor.from_pretrained(BASE_MODEL)
model = AutoModelForMultimodalLM.from_pretrained(
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
# Drive-safe CCP-DatasetNinja loader:
#   1) Bounded-depth root discovery (NO rglob - Drive FUSE makes it hang).
#   2) rsync mirror Drive -> local /content/ SSD (one-shot, ~30-60s vs ~30min
#      of per-file Drive RPCs).
#   3) tqdm progress bar.
#   4) Parsed records cached to /content/ccp_records.json so kernel restarts
#      don't redo the parse.
import base64, io, json, zlib
import numpy as np
from pathlib import Path
from PIL import Image
from tqdm.auto import tqdm

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

LOCAL_CCP = Path('/content/ccp_local')
CCP_CACHE = Path('/content/ccp_records.json')


def _find_dataset_root(base: Path) -> Path:
    \"\"\"Return the directory containing both img/ and ann/. Check up to
    depth 3 only -- Drive FUSE is too slow for rglob.\"\"\"
    candidates = [base]
    try:
        candidates += [p for p in base.iterdir() if p.is_dir()][:50]
    except (PermissionError, OSError):
        pass
    for p in list(candidates):
        if p == base: continue
        try:
            candidates += [q for q in p.iterdir() if q.is_dir()][:20]
        except (PermissionError, OSError):
            pass
    for c in candidates:
        if (c / 'img').is_dir() and (c / 'ann').is_dir():
            return c
    raise FileNotFoundError(
        f'No img/ + ann/ pair found under {base} (depth 3). '
        f'Inspect with: !find {base} -maxdepth 3 -type d | head -30'
    )


if not (LOCAL_CCP / '_done').exists():
    print('Locating CCP root on Drive...')
    drive_root = _find_dataset_root(CCP_DIR)
    print(f'Found: {drive_root}')
    print(f'Mirroring to {LOCAL_CCP} (one-time)...')
    LOCAL_CCP.mkdir(parents=True, exist_ok=True)
    !rsync -a --info=progress2 --exclude='*/.ipynb_checkpoints' \\
        \"{drive_root}/\" \"{LOCAL_CCP}/\"
    (LOCAL_CCP / '_done').touch()
    print('Mirror complete.')
else:
    print(f'Using existing local mirror at {LOCAL_CCP}')

ROOT = LOCAL_CCP


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
    if CCP_CACHE.exists():
        print(f'Loading parsed records from cache: {CCP_CACHE}')
        return [tuple(r) for r in json.loads(CCP_CACHE.read_text())]

    img_files = sorted((ROOT / 'img').glob('*.jpg'))
    print(f'Found {len(img_files)} jpgs; parsing annotations...')
    records = []
    for jpg in tqdm(img_files, desc='CCP', unit='img'):
        ann_path = ROOT / 'ann' / f'{jpg.name}.json'
        if not ann_path.exists():
            continue
        try:
            ann = json.loads(ann_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        w = int(ann.get('size', {}).get('width') or 0)
        h = int(ann.get('size', {}).get('height') or 0)
        if not (w and h):
            try:
                with Image.open(jpg) as im:
                    w, h = im.size
            except Exception:
                continue
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

    CCP_CACHE.write_text(json.dumps(records))
    print(f'Cached {len(records)} records to {CCP_CACHE}')
    return records


ccp_records = load_ccp_records()
print(f'\\nCCP records (>=1 garment): {len(ccp_records)}')
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
import hashlib

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

    # Two-step processing.
    # apply_chat_template(tokenize=True) doesn't reliably extract inline
    # PIL images from {'type':'image','image': pil} content parts on
    # Gemma-4. The image processor never runs, so 'image_position_ids'
    # is missing from the output and the SigLIP vision tower crashes
    # later with:
    #   AttributeError: 'bool' object has no attribute 'all'
    # Reliable workaround: render the template to text first (no
    # tokenize), then call the processor with text= AND images=
    # explicitly. The chat template's '{type: image}' placeholder
    # is paired with the PIL image passed via images=.
    messages_full = [
        {'role': 'system',    'content': SYSTEM_PROMPT},
        {'role': 'user',      'content': [
            {'type': 'image'},
            {'type': 'text', 'text': USER_INSTRUCTION},
        ]},
        {'role': 'assistant', 'content': target_json},
    ]
    messages_prompt = messages_full[:2]

    full_text = processor.apply_chat_template(
        messages_full,
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,
    )
    prompt_text = processor.apply_chat_template(
        messages_prompt,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    full   = processor(text=full_text,   images=image, return_tensors='pt', padding=False)
    prompt = processor(text=prompt_text, images=image, return_tensors='pt', padding=False)

    input_ids = full['input_ids'][0]
    labels    = input_ids.clone()
    n_prompt  = prompt['input_ids'].shape[1]
    labels[:n_prompt] = ignore_index

    # Forward every tensor the processor returned (squeeze the batch dim).
    out = {}
    for k, v in full.items():
        if torch.is_tensor(v):
            out[k] = v[0] if v.shape[0] == 1 else v
        else:
            out[k] = v
    out['labels'] = labels
    return out


ex = build_example(train[0])
print('build_example keys :', list(ex.keys()))
for k, v in ex.items():
    shape = tuple(v.shape) if torch.is_tensor(v) else type(v).__name__
    dtype = v.dtype if torch.is_tensor(v) else ''
    print(f'  {k:24s} shape={shape}  dtype={dtype}')
assert 'image_position_ids' in ex, (
    \"image_position_ids missing -- processor didn't see the image. \"
    \"Check transformers version >= 5.5.0.\"
)
print(f'  loss-active tokens : {(ex[\"labels\"] != -100).sum().item()}')
"""

CODE_COLLATOR = """\
from dataclasses import dataclass

@dataclass
class GemmaVLCollator:
    pad_token_id: int
    ignore_index: int = -100

    # Class attribute — ships with the pickled collator, so DataLoader
    # workers see it whether they fork or spawn. Module-level globals
    # do not reliably survive cross-process fan-out.
    SEQ_KEYS = frozenset({
        'input_ids', 'labels', 'attention_mask',
        'token_type_ids', 'mm_token_type_ids',
    })

    def __call__(self, batch):
        max_seq = max(b['input_ids'].shape[0] for b in batch)
        keys    = list(batch[0].keys())
        out     = {}
        for k in keys:
            samples = [b[k] for b in batch if k in b]
            if not samples or not torch.is_tensor(samples[0]):
                continue
            if k in self.SEQ_KEYS:
                pad_val = {
                    'input_ids':         self.pad_token_id,
                    'labels':            self.ignore_index,
                    'attention_mask':    0,
                    'token_type_ids':    0,
                    'mm_token_type_ids': 0,
                }.get(k, 0)
                padded = [
                    torch.cat([s, torch.full((max_seq - s.shape[0],),
                                              pad_val, dtype=s.dtype)])
                    for s in samples
                ]
                out[k] = torch.stack(padded)
            else:
                # Multi-dim tensors (pixel_values, image_position_ids, ...).
                # Visual token budget is fixed (1120) so patch counts are
                # uniform across the batch -- direct stack works.
                out[k] = torch.stack(samples)
        return out


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
from tqdm.auto import tqdm

# Sanity-eval budget. Set to None to evaluate the full test split (slow!).
EVAL_LIMIT = 100

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
    \"\"\"Two-step pattern (same as build_example): render chat template
    to text first, then call the processor with text= AND images=
    explicitly. apply_chat_template(tokenize=True) does not reliably
    feed inline PIL images into Gemma4ImageProcessor, which means
    image_position_ids would be missing from the output and the SigLIP
    vision tower would crash.\"\"\"
    image = _PIL_Image.open(img_path).convert('RGB')
    msgs = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user',   'content': [
            {'type': 'image'},
            {'type': 'text', 'text': USER_INSTRUCTION},
        ]},
    ]
    text = processor.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    enc = processor(text=text, images=image, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=200,            # plenty for a 5-item JSON array
            do_sample=False,
            pad_token_id=processor.tokenizer.pad_token_id,
        )
    return _safe_parse(
        processor.tokenizer.decode(
            out[0][enc['input_ids'].shape[1]:],
            skip_special_tokens=True,
        )
    )


records = test_ds.recs[:EVAL_LIMIT] if EVAL_LIMIT else test_ds.recs
print(f'Evaluating on {len(records)} / {len(test_ds.recs)} test records '
      f'(EVAL_LIMIT={EVAL_LIMIT})')

ious, n_gt, n_pred, n_match, n_err = [], 0, 0, 0, 0
t0 = time.perf_counter()

for img_path, target_json, _src in tqdm(records, desc='eval', unit='img'):
    try:
        gts = json.loads(target_json)
        with _PIL_Image.open(img_path) as im:
            w, h = im.size
        gts_px = [_denorm(g['region']['bbox'], w, h) for g in gts]
        preds = _predict(img_path)
    except Exception:
        n_err += 1
        continue

    if not isinstance(preds, list):
        n_gt += len(gts_px)
        continue

    preds_px = []
    for p in preds:
        if not isinstance(p, dict): continue
        bb = (p.get('region') or {}).get('bbox')
        if isinstance(bb, list) and len(bb) == 4:
            preds_px.append(_denorm(bb, w, h))

    triples = sorted(
        [(_iou(p, g), pi, gi)
         for pi, p in enumerate(preds_px)
         for gi, g in enumerate(gts_px)],
        reverse=True,
    )
    up, ug = set(), set()
    for iou, pi, gi in triples:
        if pi in up or gi in ug: continue
        up.add(pi); ug.add(gi); ious.append(iou)
        if iou >= 0.5: n_match += 1

    n_gt   += len(gts_px)
    n_pred += len(preds_px)

el = time.perf_counter() - t0
print()
print(f'tested              : {len(records)} in {el:.1f}s ({el/max(len(records),1):.2f}s/img)')
print(f'errors              : {n_err}')
print(f'mean IoU            : {np.mean(ious):.3f}' if ious else 'mean IoU            : --')
print(f'recall @ IoU=0.5    : {n_match/n_gt:.3f}' if n_gt   else 'recall              : --')
print(f'precision @ IoU=0.5 : {n_match/n_pred:.3f}' if n_pred else 'precision           : --')
print(f'avg preds / image   : {n_pred/len(records):.2f}')
"""


# ─────────────────────────────────────────────────────────────
# Section 12-13 — Adapter-only GGUF export
# ─────────────────────────────────────────────────────────────
MD_QUANT = """\
---

## 12-13. Adapter-only export (skip the merge)

We deliberately skip the full HF -> GGUF merge + convert path because
upstream `convert_hf_to_gguf.py` doesn't yet recognise Gemma-4
multimodal architectures (`Gemma4ForConditionalGeneration`). Instead
we ship Eyes as a **3-file bundle**:

* Pre-converted Q4_K_M base from `ggml-org/gemma-4-E2B-it-GGUF`
* Pre-converted vision projector from the same repo
* Our **trained LoRA delta** as a separate GGUF (~50 MB)

llama.cpp combines them at load time via `--lora`, so there's no
merge step on either side. Bonus: the base + projector are reusable
across re-trains, so iterating on Eyes is just a 30 s LoRA export
instead of a 30 min merge + Q4_K_M run.

For Phase 2 (audio LoRA on top of vision-Eyes) we just train a
second LoRA and stack it via repeated `--lora` flags.
"""

CODE_MERGE = """\
# Save the adapter only -- skip the merge entirely.
import re, shutil, pathlib
from peft import PeftModel

LOCAL_BASE  = pathlib.Path('/content/eyes_v4_local')
ADAPTER_DIR = LOCAL_BASE / 'adapter'
LOCAL_BASE.mkdir(parents=True, exist_ok=True)
if ADAPTER_DIR.exists():
    shutil.rmtree(ADAPTER_DIR)
ADAPTER_DIR.mkdir(parents=True)


def _try_inmem_save():
    \"\"\"First attempt: model.save_pretrained() on a PeftModel saves
    just the adapter. Returns True if the saved safetensors are
    non-empty (> 1 KB). False indicates the in-memory adapter has
    already been merged in place and contains no deltas.\"\"\"
    if not isinstance(model, PeftModel):
        return False
    model.save_pretrained(str(ADAPTER_DIR))
    sf = ADAPTER_DIR / 'adapter_model.safetensors'
    return sf.exists() and sf.stat().st_size > 1024


def _from_disk_checkpoint():
    \"\"\"Fallback: the in-memory adapter is empty (an earlier
    merge_adapter() call baked the LoRA deltas into the base
    linears). Recover by copying the highest-step on-disk checkpoint
    from {OUT_RUN}/checkpoint-* — those snapshots have un-merged
    adapters frozen at the step they were saved.\"\"\"
    ckpts = sorted(
        pathlib.Path(OUT_RUN).glob('checkpoint-*'),
        key=lambda p: int(re.search(r'checkpoint-(\\d+)', p.name).group(1)),
    )
    if not ckpts:
        raise RuntimeError(
            f'No checkpoints found in {OUT_RUN}. Re-train.'
        )

    # Walk newest -> oldest until we find a non-empty adapter.
    chosen = None
    for ck in reversed(ckpts):
        sf = ck / 'adapter_model.safetensors'
        if sf.exists() and sf.stat().st_size > 1024:
            chosen = ck
            break
    if chosen is None:
        raise RuntimeError(
            'All checkpoints have empty adapter files. Re-train.'
        )
    print(f'Recovering adapter from on-disk checkpoint: {chosen.name}')

    # Wipe and refill ADAPTER_DIR
    if ADAPTER_DIR.exists():
        shutil.rmtree(ADAPTER_DIR)
    ADAPTER_DIR.mkdir(parents=True)
    keep = ('adapter_', 'tokenizer', 'special_tokens', 'chat_template', 'README')
    for p in chosen.iterdir():
        if p.is_file() and p.name.startswith(keep):
            shutil.copy2(p, ADAPTER_DIR / p.name)


if _try_inmem_save():
    print('In-memory adapter saved.')
else:
    print('In-memory adapter is empty (merged in place); falling back to '
          'on-disk checkpoint recovery...')
    _from_disk_checkpoint()

print('\\nFinal adapter files:')
for p in sorted(ADAPTER_DIR.iterdir()):
    print(f'  {p.name:40s} {p.stat().st_size // 1024} KB')

sf_final = ADAPTER_DIR / 'adapter_model.safetensors'
assert sf_final.exists() and sf_final.stat().st_size > 1024, \\
    f'adapter_model.safetensors empty/missing ({sf_final.stat().st_size} bytes)'
"""

CODE_GGUF_BUILD = """\
# Build llama.cpp from master (we only need the LoRA converter +
# llama-cli for the probe; full quant binaries not needed any more).
%cd /content
![ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp llama.cpp
%cd /content/llama.cpp
!git pull --ff-only 2>&1 | tail -3
!pip install -q -r requirements/requirements-convert_lora_to_gguf.txt 2>&1 | tail -3
"""

CODE_GGUF_TEXT = """\
# Download pre-converted base + mmproj from HF Hub. ggml-org ships
# Q8_0 (4.97 GB) and bf16 (9.3 GB) only; no Q4_K_M as of May 2026.
# Q8_0 is the right pick: small enough for Hetzner, marginally higher
# quality than Q4_K_M anyway.
from huggingface_hub import hf_hub_download

GGUF_REPO = 'ggml-org/gemma-4-E2B-it-GGUF'
print(f'Downloading pre-converted artifacts from {GGUF_REPO}...')
BASE_GGUF = pathlib.Path(hf_hub_download(
    GGUF_REPO, 'gemma-4-E2B-it-Q8_0.gguf', local_dir=str(LOCAL_BASE)))
MMPROJ_GGUF = pathlib.Path(hf_hub_download(
    GGUF_REPO, 'mmproj-gemma-4-E2B-it-Q8_0.gguf', local_dir=str(LOCAL_BASE)))
print(f'  base   : {BASE_GGUF.name}    ({BASE_GGUF.stat().st_size / 1024**3:.2f} GB)')
print(f'  mmproj : {MMPROJ_GGUF.name}  ({MMPROJ_GGUF.stat().st_size / 1024**2:.0f} MB)')
"""

CODE_GGUF_MMPROJ = """\
# Convert the LoRA adapter to GGUF. This is the ONLY conversion we
# do ourselves -- much narrower than full convert_hf_to_gguf.py and
# works for Gemma-4 today (only needs the base architecture's tensor
# names, which llama.cpp does know).
LORA_GGUF = LOCAL_BASE / 'eyes_v4_lora.gguf'

!python /content/llama.cpp/convert_lora_to_gguf.py \\
    --base {BASE_MODEL} \\
    --outfile {LORA_GGUF} \\
    {ADAPTER_DIR}

assert LORA_GGUF.exists(), 'LoRA GGUF conversion failed'
print(f'LoRA delta GGUF: {LORA_GGUF}  ({LORA_GGUF.stat().st_size / 1024**2:.1f} MB)')
"""

CODE_GGUF_QUANT = """\
# No quantization step -- the base GGUF is already Q4_K_M and the
# LoRA delta is fp16 (LoRA weights are tiny so quant offers no win).
# This cell is just a status check before the rsync.
print('=== Eyes v4 GGUF bundle ===')
for p in [BASE_GGUF, MMPROJ_GGUF, LORA_GGUF]:
    print(f'  {p.name:50s} {p.stat().st_size / 1024**2:>8.1f} MB')
"""

CODE_GGUF_RSYNC = """\
# Stash the bundle to Drive. Only the LoRA delta is unique to this
# Eyes version; base + mmproj are stock and don't need re-uploading
# every train run, but copying them once means Hetzner deploy is a
# self-contained 3-scp.
import shutil

DRIVE_OUT = pathlib.Path('/content/drive/MyDrive/DressApp_Gemma4_E2B_Training')
DRIVE_OUT.mkdir(parents=True, exist_ok=True)

DRIVE_LORA   = DRIVE_OUT / LORA_GGUF.name
DRIVE_BASE   = DRIVE_OUT / BASE_GGUF.name
DRIVE_MMPROJ = DRIVE_OUT / MMPROJ_GGUF.name

print(f'Copying LoRA delta ({LORA_GGUF.stat().st_size / 1024**2:.1f} MB) to Drive...')
shutil.copy2(LORA_GGUF, DRIVE_LORA)

if not DRIVE_BASE.exists() or DRIVE_BASE.stat().st_size != BASE_GGUF.stat().st_size:
    print(f'Copying base ({BASE_GGUF.stat().st_size / 1024**3:.2f} GB) to Drive...')
    shutil.copy2(BASE_GGUF, DRIVE_BASE)
else:
    print('Base already on Drive, skipping.')

if not DRIVE_MMPROJ.exists() or DRIVE_MMPROJ.stat().st_size != MMPROJ_GGUF.stat().st_size:
    print(f'Copying mmproj ({MMPROJ_GGUF.stat().st_size / 1024**3:.2f} GB) to Drive...')
    shutil.copy2(MMPROJ_GGUF, DRIVE_MMPROJ)
else:
    print('mmproj already on Drive, skipping.')

print()
print('=== Drive bundle ready for scp -> Hetzner ===')
for p in (DRIVE_LORA, DRIVE_BASE, DRIVE_MMPROJ):
    print(f'  {p}')
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
# Prebuilt CUDA wheel (fast). If your Colab runtime is on a CUDA version
# different from 12.x, the wheel may still install fine via forward
# compat. If it doesn't, drop --extra-index-url to fall back to a
# source build (slow, ~5-10 min compile).
%pip install -q --upgrade \\
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 \\
    --prefer-binary \\
    'llama-cpp-python>=0.3.0'

# Sanity-check the install worked.
import importlib
_cf = importlib.import_module('llama_cpp.llama_chat_format')
print('llama-cpp-python OK. Available handlers:',
      [n for n in dir(_cf) if 'Handler' in n][:10])
"""

CODE_PROBE_RUN = """\
import random, json, importlib, pathlib
from llama_cpp import Llama

# Use importlib so static checkers (Pyright/Pylance) don't whine about
# the import not existing pre-install. Llava15ChatHandler is the
# universal Gemma/PaliGemma/LLaVA-family vision handler.
_cf = importlib.import_module('llama_cpp.llama_chat_format')
VisionHandler = _cf.Llava15ChatHandler

handler = VisionHandler(clip_model_path=str(MMPROJ_GGUF), verbose=False)
llm = Llama(
    model_path=str(BASE_GGUF),
    chat_handler=handler,
    n_ctx=4096,
    n_gpu_layers=-1,
    lora_path=str(LORA_GGUF),     # runtime-applied Eyes LoRA delta
    verbose=False,
)

random.seed(42)
samples = random.sample(test_ds.recs, k=min(5, len(test_ds.recs)))

for img_path, target_json, src in samples:
    print('=' * 70)
    print(f'Image  : {pathlib.Path(img_path).name}  (source: {src})')
    resp = llm.create_chat_completion(
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user',   'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'file://{img_path}'}},
                {'type': 'text', 'text': USER_INSTRUCTION},
            ]},
        ],
        temperature=0.0,
        max_tokens=200,
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
    # Section 6 (DF inspect + on-disk loader) removed -- df_records is now
    # populated directly by the Marqo loader cell in Section 3.
    md(MD_SPLIT),  code(CODE_SPLIT),
    md(MD_CONV),   code(CODE_PROMPT), code(CODE_BUILD_EXAMPLE),
                   code(CODE_COLLATOR), code(CODE_DATASET_CLASS),
    md(MD_LORA),   code(CODE_LORA),
    md(MD_TRAIN),  code(CODE_TRAIN_ARGS), code(CODE_TRAIN_RUN),
    md(MD_EVAL),   code(CODE_EVAL),
    md(MD_QUANT),  code(CODE_MERGE),
                   code(CODE_GGUF_BUILD), code(CODE_GGUF_TEXT),
                   code(CODE_GGUF_MMPROJ), code(CODE_GGUF_QUANT),
                   code(CODE_GGUF_RSYNC),
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
