#!/usr/bin/env python3
"""Generator for ``/app/docs/notebooks/Eyes_FineTune_v4_Gemma3n.ipynb``.

Reproduces Eyes from scratch on the **correct** Gemma-3n
(``google/gemma-3n-e2b-it``) base, using TWO datasets:

* DeepFashion-Multimodal (Kaggle, ~12 k images)
* CCP-DatasetNinja (~2 k images, already mounted in user's Drive)

Replaces the prior ``Eyes_FineTune_v4_OnePass.ipynb`` which targeted the
wrong (Gemma-3) class. The previous v3-merged checkpoint produced by
an earlier agent is irrecoverable — it lost the audio tower, PLE
projections, and vision quant-scale tensors during a wrong-class merge.

Run::

    python3 /app/scripts/build_eyes_finetune_v4_notebook.py

Output::

    /app/docs/notebooks/Eyes_FineTune_v4_Gemma3n.ipynb
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/app/docs/notebooks/Eyes_FineTune_v4_Gemma3n.ipynb")
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
# Eyes v4 — Fine-Tune Gemma-3n-E2B on DeepFashion + CCP

> **Objective.** Train a fresh Eyes LoRA on top of Google's official
> `gemma-3n-e2b-it` checkpoint so that a single Eyes call emits a JSON
> array `[{label, category, region.bbox}, …]` covering every visible
> garment.
>
> **Why a clean restart.** The previous `Eyes_v3_Gemma4_E2B_merged`
> folder was produced by a prior agent that loaded it with
> `Gemma3ForConditionalGeneration` — the *non-n* class. That silently
> dropped the audio tower, the per-layer-embedding projections, and
> the vision quant-scale tensors during the merge, leaving a corrupt
> checkpoint we can't recover from. We start over from the official
> base on HF Hub and lay down a v4 LoRA from there.
>
> **Target runtime.** Colab Pro+ A100 (40 GB). ≈ 14 k images × 2 epochs
> with bf16 + LoRA-only training → roughly 25–35 min wall.

## Inputs

| Asset | Source / Path |
| --- | --- |
| Base model (gated) | `google/gemma-3n-e2b-it` on HF Hub |
| DeepFashion-Multimodal | Kaggle dataset `silverstone1903/deep-fashion-multimodal` |
| CCP-DatasetNinja | `/content/drive/MyDrive/ccp-DatasetNinja` |

## Outputs (written to Drive)

| Artifact | Path |
| --- | --- |
| Merged fp16 (HF format) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_Gemma3n_merged/` |
| Text-model GGUF (Q4_K_M) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4-Q4_K_M.gguf` |
| Vision projector GGUF | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/mmproj-Eyes_v4-f16.gguf` |
| Training run dir | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_run/` |

## What "freeze the weights" means here

PEFT-LoRA automatically freezes every base parameter — gradient only
flows through the injected rank-16 adapters wrapped around the text
decoder's Linear layers. On top of that, this notebook **explicitly**
sets `requires_grad=False` on:

* the SigLIP vision tower (`vision_tower.*`)
* the audio tower (`audio_tower.*` — Gemma-3n ships one even though we
  don't use audio)
* the multimodal projector (`multi_modal_projector.*`, `embed_vision.*`)
* the audio embedding projection (`embed_audio.*`)
* the per-layer-embedding projections (`per_layer_*`, `embed_tokens_per_layer`)

Belts-and-braces — these wouldn't train under LoRA anyway, but pinning
them prevents an accidental future cell from un-freezing them.
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
# you'd need to enable QLoRA — see the commented-out 4-bit block in the
# model-load cell below.
!nvidia-smi
"""

CODE_PATHS = """\
import pathlib

BASE_DIR    = pathlib.Path('/content/drive/MyDrive/DressApp_Gemma4_E2B_Training')
CCP_DIR     = pathlib.Path('/content/drive/MyDrive/ccp-DatasetNinja')
DF_DIR      = pathlib.Path('/content/deepfashion_mm')           # Kaggle extracts here
OUT_RUN     = BASE_DIR / 'Eyes_v4_run'
OUT_MERGED  = BASE_DIR / 'Eyes_v4_Gemma3n_merged'
OUT_GGUF    = BASE_DIR / 'Eyes_v4-Q4_K_M.gguf'
OUT_MMPROJ  = BASE_DIR / 'mmproj-Eyes_v4-f16.gguf'
for p in (BASE_DIR, OUT_RUN, DF_DIR.parent):
    p.mkdir(parents=True, exist_ok=True)

assert CCP_DIR.exists(), f'CCP-DatasetNinja missing at {CCP_DIR}'
print('✅ Drive paths:')
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

Same hard-earned policy as before: **only upgrade what we need**
(`transformers`, `peft`, `accelerate`), pin Pillow back to gradio's
range, leave everything else at Colab default. Add `kaggle` for the
DeepFashion download and `huggingface_hub[cli]` for the Gemma-3n auth.

If you hit an import error *above* this cell after running it,
**Runtime → Restart session** first (poisoned `sys.modules`), then
re-run from cell 1.
"""

CODE_DEPS = """\
%pip install -q --upgrade pip
%pip install -q --upgrade transformers peft accelerate
%pip install -q 'Pillow<12.0'
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
"""


# ─────────────────────────────────────────────────────────────
# Section 3 — Kaggle + HF Hub auth + DeepFashion download
# ─────────────────────────────────────────────────────────────
MD_AUTH = """\
---

## 3. Auth + dataset download

Two creds to set up:

1. **HuggingFace Hub token** — `google/gemma-3n-e2b-it` is gated. You
   must first visit the model card on HF Hub and accept Google's
   Gemma license terms with the SAME Hub account whose token you
   paste below. Get a token at <https://huggingface.co/settings/tokens>
   with `read` access.
2. **Kaggle API token** — download `kaggle.json` from
   <https://www.kaggle.com/settings/account> → "Create New Token".
   The next cell will prompt you to upload it.

Run the two cells, then the DeepFashion download cell.
"""

CODE_HF_AUTH = """\
from huggingface_hub import login as hf_login
import getpass
hf_token = getpass.getpass('HF Hub token (read access, paste hidden): ')
hf_login(token=hf_token, add_to_git_credential=False)
print('✅ Logged into HF Hub.')
"""

CODE_KAGGLE_AUTH = """\
import os, json
from google.colab import files

# Either upload kaggle.json...
os.makedirs('/root/.kaggle', exist_ok=True)
if not os.path.exists('/root/.kaggle/kaggle.json'):
    print('Upload your kaggle.json (Kaggle → Settings → API → Create New Token):')
    up = files.upload()
    fname = next(iter(up))
    with open('/root/.kaggle/kaggle.json', 'wb') as fh:
        fh.write(up[fname])
os.chmod('/root/.kaggle/kaggle.json', 0o600)
# Sanity
cfg = json.load(open('/root/.kaggle/kaggle.json'))
print(f'✅ Kaggle creds present for user: {cfg[\"username\"]}')
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
# Section 4 — Load Gemma-3n + freeze everything except text-decoder
# ─────────────────────────────────────────────────────────────
MD_LOAD = """\
---

## 4. Load `google/gemma-3n-e2b-it` and aggressively freeze

We use `Gemma3nForConditionalGeneration` (note the `n`). This is the
correct multimodal class for Gemma-3n — it knows about the audio
tower, the per-layer embeddings, and the SigLIP vision tower.

Right after loading we freeze, by name match, everything that is *not*
inside the text decoder. PEFT-LoRA would freeze them anyway, but this
explicit pass is a circuit-breaker against any future cell calling
`.train()` on the whole model.
"""

CODE_LOAD = """\
import torch
from transformers import AutoProcessor, Gemma3nForConditionalGeneration

BASE_MODEL = 'google/gemma-3n-e2b-it'

processor = AutoProcessor.from_pretrained(BASE_MODEL)
model = Gemma3nForConditionalGeneration.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    attn_implementation='eager',           # safest for Gemma-3n LoRA
    device_map={'': 0},
)

# Some processor builds ship without an explicit chat template — set the
# canonical Gemma-3 chat format so train + inference see the same surface.
if processor.chat_template is None or '<start_of_turn>' not in processor.chat_template:
    processor.chat_template = (
        "{% for message in messages %}"
        "<start_of_turn>{{ message['role'] }}\\n"
        "{% for content in message['content'] %}"
        "{% if content['type'] == 'image' %}<image>{% else %}{{ content['text'] }}{% endif %}"
        "{% endfor %}"
        "<end_of_turn>\\n"
        "{% endfor %}"
        "{% if add_generation_prompt %}<start_of_turn>model\\n{% endif %}"
    )

# === FREEZE EVERYTHING THAT IS NOT THE TEXT DECODER ===
#
# Gemma-3n has FOUR sub-modules that we never want to train on a small
# corpus:
#   * vision_tower         — SigLIP image encoder
#   * audio_tower          — universal audio encoder (we never feed it audio)
#   * multi_modal_projector + embed_vision  — image-token projection
#   * embed_audio          — audio-token projection (unused)
#   * per_layer_*, embed_tokens_per_layer  — Per-Layer Embedding bank
#
# Anything matching the substrings below stays frozen.
FROZEN_SUBSTRINGS = (
    'vision_tower',
    'audio_tower',
    'multi_modal_projector',
    'embed_vision',
    'embed_audio',
    'per_layer_projection',
    'per_layer_input_gate',
    'per_layer_model_projection',
    'post_per_layer_input_norm',
    'embed_tokens_per_layer',
    'layer_scalar',
)

n_frozen = n_trainable = 0
for name, p in model.named_parameters():
    if any(sub in name for sub in FROZEN_SUBSTRINGS):
        p.requires_grad = False
        n_frozen += p.numel()
    else:
        n_trainable += p.numel()        # may still get LoRA-frozen below

print(f'Frozen (vision/audio/PLE/projector) : {n_frozen / 1e6:7.1f} M params')
print(f'Pre-LoRA trainable (text decoder)   : {n_trainable / 1e6:7.1f} M params')
print(f'Total                                : {(n_frozen + n_trainable) / 1e9:6.2f} B params')
"""


# ─────────────────────────────────────────────────────────────
# Section 5 — CCP dataset loader (same as v3)
# ─────────────────────────────────────────────────────────────
MD_CCP = """\
---

## 5. Build training records from CCP-DatasetNinja

Decode Supervise.ly bitmap masks → enclosing pixel bbox → DressApp
category → normalised 0..1000 grid. Produces `(image_path,
target_json_str)` tuples.
"""

CODE_CCP_LOADER = """\
import base64, io, json, zlib, glob, hashlib
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
print(f'CCP records (≥1 garment): {len(ccp_records)}')
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
bounding boxes for the visible garment(s). We:

1. Walk the unzipped dataset directory.
2. Identify the attribute / bbox annotation file (the layout varies by
   version — the loader is defensive about it).
3. For each image, map the DeepFashion attribute class to a DressApp
   category and emit one `{label, category, region.bbox}` entry per
   annotated garment.

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
# The loader below is permissive — it tries a few common paths and a
# few common annotation column schemas, and skips images it can't parse.

import csv, glob, json, pathlib
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
    # Fallback — first sub-dir with a lot of jpgs
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
        # No annotation file? Then we can't extract bboxes — bail out.
        print('⚠ No annotation file found; skipping DeepFashion.')
        return records

    # Strategy A — CSV with columns like image_name,category,x1,y1,x2,y2
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

    # Strategy B — JSON list of dicts
    if ann_path.suffix == '.json':
        try:
            data = json.load(open(ann_path))
            if isinstance(data, dict) and 'annotations' in data:
                data = data['annotations']
            for row in data:
                # Map adaptively — the column names will vary.
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

    # Strategy C — fallback: just enumerate images with no bbox.
    # Better than nothing — uses the whole frame as the bbox.
    print('⚠ Annotation format not recognised; falling back to whole-frame bboxes.')
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

Identical to v3's design — we mask the user-side tokens so gradient
only flows through the JSON the model is supposed to emit.
"""

CODE_PROMPT = """\
SYSTEM_PROMPT = (
    \"You are DressApp Eyes, a vision model specialised in clothing.\\n\"
    \"You receive ONE photograph and return ONLY valid JSON.\\n\\n\"
    \"Schema: a JSON array. Each element describes ONE distinct visible\\n\"
    \"garment, accessory, or footwear item:\\n\"
    \"  { \\\"label\\\":    string,\\n\"
    \"    \\\"category\\\": one of [Top|Bottom|Outerwear|Full-body|Footwear|Accessory],\\n\"
    \"    \\\"region\\\":   { \\\"bbox\\\": [ymin, xmin, ymax, xmax] }  // 0..1000 grid\\n\"
    \"  }\\n\\n\"
    \"Rules:\\n\"
    \" - Always return an array. A single-garment photo returns a one-element array.\\n\"
    \" - List EVERY distinct garment. Layered outfits = N elements.\\n\"
    \" - Skip skin, hair, body parts, backgrounds.\\n\"
    \" - bbox values are integers on a 0..1000 grid, NOT pixels.\\n\"
    \" - No prose, no markdown — JSON only.\\n\"
)
USER_INSTRUCTION = 'Analyze this outfit photograph and return the JSON array.'
print(SYSTEM_PROMPT[:200], '...')
"""

CODE_BUILD_EXAMPLE = """\
import torch
from PIL import Image as _PIL_Image

def build_example(record, *, ignore_index=-100):
    img_path, target_json, _source = record
    image = _PIL_Image.open(img_path).convert('RGB')

    messages_full = [
        {'role': 'user', 'content': [
            {'type': 'image'},
            {'type': 'text', 'text': SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
        ]},
        {'role': 'model', 'content': [{'type': 'text', 'text': target_json}]},
    ]
    messages_prompt = messages_full[:1]
    full_text   = processor.apply_chat_template(messages_full,   add_generation_prompt=False, tokenize=False)
    prompt_text = processor.apply_chat_template(messages_prompt, add_generation_prompt=True,  tokenize=False)
    full   = processor(text=full_text,   images=image, return_tensors='pt', padding=False)
    prompt = processor(text=prompt_text, images=image, return_tensors='pt', padding=False)

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

A100 + bf16 → no QLoRA. Batch 2 × grad-accum 8 = effective 16. ≈14 k
records ÷ 16 ≈ 875 steps / epoch × 2 epochs = ~1750 total steps.
Checkpoint to Drive every 200 steps for disconnect insurance.
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

Same metric as `/app/scripts/run_eyes_benchmark.py` so v4 numbers are
directly comparable to the v3 (Gemini-Flash) and SegFormer+per-crop
benches we recorded earlier:

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
    msgs = [{'role':'user','content':[
        {'type':'image'},
        {'type':'text','text':SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
    ]}]
    text = processor.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    enc = processor(text=text, images=image, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=512, do_sample=False,
                              pad_token_id=processor.tokenizer.pad_token_id)
    return _safe_parse(processor.tokenizer.decode(out[0][enc['input_ids'].shape[1]:], skip_special_tokens=True))

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
    triples = sorted([(_iou(p, g), pi, gi) for pi, p in enumerate(preds_px) for gi, g in enumerate(gts_px)], reverse=True)
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
# Section 12 — Merge LoRA + save fp16
# ─────────────────────────────────────────────────────────────
MD_MERGE = """\
---

## 12. Merge LoRA + save fp16 to Drive
"""

CODE_MERGE = """\
merged = model.merge_and_unload()
OUT_MERGED.mkdir(parents=True, exist_ok=True)
merged.save_pretrained(str(OUT_MERGED), safe_serialization=True, max_shard_size='4GB')
processor.save_pretrained(str(OUT_MERGED))

total_gb = sum(p.stat().st_size for p in OUT_MERGED.rglob('*')) / (1024**3)
print(f'✅ Saved merged fp16 to {OUT_MERGED} ({total_gb:.2f} GB)')
"""


# ─────────────────────────────────────────────────────────────
# Section 13 — Quantize to GGUF (text + mmproj)
# ─────────────────────────────────────────────────────────────
MD_QUANT = """\
---

## 13. Convert to GGUF + quantize to Q4_K_M

Two artifacts get produced this time:

1. **Text-model GGUF** (Q4_K_M, ~3 GB) — the language decoder + token
   embeddings, what the Hetzner llama-server actually runs.
2. **Vision projector GGUF** (fp16, ~1 GB) — the SigLIP + projector
   from `gemma-3n-e2b-it`. *Different from v2's `mmproj-Gemma4E2B-f16.gguf`*
   because we're starting from a different base — so this REPLACES
   v2's mmproj on the Hetzner pod, both files ship together.

llama.cpp's `convert_hf_to_gguf.py` knows how to split a Gemma-3n
multimodal checkpoint into these two pieces when invoked with
`--mmproj` for the projector run.
"""

CODE_GGUF_BUILD = """\
%cd /content
![ -d llama.cpp ] || git clone --depth 1 https://github.com/ggerganov/llama.cpp llama.cpp
%cd /content/llama.cpp
!pip install -q -r requirements/requirements-convert_hf_to_gguf.txt
!cmake -B build -DGGML_CUDA=ON 2>&1 | tail -3
!cmake --build build --config Release --target llama-quantize -j 2>&1 | tail -3
"""

CODE_GGUF_TEXT = """\
F16_GGUF = OUT_RUN / 'Eyes_v4-f16.gguf'

# Convert the text decoder to GGUF in fp16.
!python /content/llama.cpp/convert_hf_to_gguf.py \\
    {OUT_MERGED} \\
    --outtype f16 \\
    --outfile {F16_GGUF}

print('fp16 text GGUF size:', round(F16_GGUF.stat().st_size / 1024**3, 2), 'GB')
"""

CODE_GGUF_MMPROJ = """\
# Convert the vision tower + multimodal projector to its own GGUF.
# Newer llama.cpp ships a dedicated path; on older clones, the same
# convert_hf_to_gguf.py with --mmproj is the right invocation.
!python /content/llama.cpp/convert_hf_to_gguf.py \\
    {OUT_MERGED} \\
    --mmproj \\
    --outtype f16 \\
    --outfile {OUT_MMPROJ}

print('mmproj fp16 size:', round(OUT_MMPROJ.stat().st_size / 1024**3, 2), 'GB')
"""

CODE_GGUF_QUANT = """\
# Quantize the TEXT model only (mmproj stays fp16 — image-tower
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

Confirms the new artifact pair loads together, emits valid JSON, and
returns multi-element arrays on multi-garment photos. If THIS works,
the Hetzner deploy will too.
"""

CODE_PROBE_INSTALL = """\
%pip install -q --upgrade \\
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 \\
    'llama-cpp-python'
"""

CODE_PROBE_RUN = """\
import random, json
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Gemma3ChatHandler

handler = Gemma3ChatHandler(clip_model_path=str(OUT_MMPROJ))
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
    print('═' * 70)
    print(f'Image  : {pathlib.Path(img_path).name}  (source: {src})')
    resp = llm.create_chat_completion(
        messages=[
            {'role':'user','content':[
                {'type':'image_url','image_url':{'url': f'file://{img_path}'}},
                {'type':'text','text':SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
            ]},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp['choices'][0]['message']['content']
    parsed = _safe_parse(raw)
    print('Predicted :', json.dumps(parsed, indent=2)[:600] if parsed else f'(unparseable) raw={raw[:200]}')
    print('Truth     :', json.dumps(json.loads(target_json), indent=2)[:600])
"""


# ─────────────────────────────────────────────────────────────
# Section 15 — Done / hand-off
# ─────────────────────────────────────────────────────────────
MD_DONE = """\
---

## ✅ Done — Hetzner deploy hand-off

Both GGUF artifacts ship together this time:

```bash
# on the Hetzner box, replace the running v2/v3 pair with the new v4 pair
scp Eyes_v4-Q4_K_M.gguf       hetzner:/srv/eyes/models/
scp mmproj-Eyes_v4-f16.gguf   hetzner:/srv/eyes/models/

# update the llama-server invocation to point to the new files:
#   --model      /srv/eyes/models/Eyes_v4-Q4_K_M.gguf
#   --mmproj     /srv/eyes/models/mmproj-Eyes_v4-f16.gguf
docker compose restart eyes
```

Then re-run the in-pod benchmark from the chat thread to validate the
gate end-to-end through the FastAPI bridge:

```bash
/root/.venv/bin/python /app/scripts/run_eyes_benchmark.py \\
    --analyzer=one_pass --limit=30
```

If `recall@0.5 ≥ 0.8` holds and `mean IoU ≥ 0.6`, you can un-retire
`EYES_ONE_PASS=true` in production and ship the simpler one-call path
back into the closet analyze flow.
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
