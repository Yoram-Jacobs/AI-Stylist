#!/usr/bin/env python3
"""Generator for ``/app/docs/notebooks/Eyes_FineTune_v4_OnePass.ipynb``.

This script builds the LoRA fine-tuning notebook from raw Python source
strings rather than hand-crafting .ipynb JSON, so the cells stay
diff-friendly and the notebook can be regenerated reproducibly when the
training protocol changes.

Run from anywhere::

    python3 /app/scripts/build_eyes_finetune_notebook.py

Output::

    /app/docs/notebooks/Eyes_FineTune_v4_OnePass.ipynb

The notebook targets:
    * Colab Pro+ A100 (40 GB VRAM, bf16, no 4-bit quant needed)
    * Inputs in user's Drive:
        - /content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v3_Gemma4_E2B_merged
        - /content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v2_Gemma4e2b/mmproj-Gemma4E2B-f16.gguf  (reused as-is)
        - /content/drive/MyDrive/ccp-DatasetNinja  (full ~2 k corpus)
    * Output back to Drive:
        - .../Eyes_v4_Gemma4_E2B_merged/        (fp16 HF format)
        - .../Eyes_v4_Q4_K_M.gguf                (production-ready)
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/app/docs/notebooks/Eyes_FineTune_v4_OnePass.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)


def md(text: str) -> dict:
    """Build a Jupyter markdown cell from a multi-line string."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    """Build a Jupyter code cell from a multi-line string."""
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


# ──────────────────────────────────────────────────────────────────────
# 1. Header
# ──────────────────────────────────────────────────────────────────────
MD_TITLE = """\
# Eyes v4 — Fine-Tune on CCP-DatasetNinja (multi-garment bbox)

> **Objective.** Continue fine-tuning `Eyes_v3_Gemma4_E2B_merged` so that
> a single Eyes call on an outfit photo returns a **JSON array** of
> `{label, category, region.bbox}` per visible garment — the failure
> mode that the May-2026 CCP-Ninja benchmark exposed (Gemini-2.5-Flash
> returned exactly 1 garment on 30/30 images, regardless of prompt).
>
> **Output.** A new fp16 merged checkpoint + a Q4_K_M GGUF artifact that
> drops into the existing Hetzner inference container alongside the
> unchanged `mmproj-Gemma4E2B-f16.gguf` (vision tower is frozen during
> LoRA so the projector doesn't need re-quantizing).
>
> **Runtime budget.** Colab Pro+ **A100 40 GB**. ~30 min for 3 epochs
> over the full ~2 k corpus.

## Inputs (in your Google Drive)

| Asset | Path |
| --- | --- |
| Training base (fp16, HF format) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v3_Gemma4_E2B_merged` |
| Reusable mmproj (vision tower) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v2_Gemma4e2b/mmproj-Gemma4E2B-f16.gguf` |
| CCP-DatasetNinja corpus | `/content/drive/MyDrive/ccp-DatasetNinja` |

## Outputs (written back to Drive)

| Artifact | Path |
| --- | --- |
| Merged fp16 (next training base) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_Gemma4_E2B_merged` |
| Q4_K_M GGUF (deploy artifact) | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_Q4_K_M.gguf` |
| Training log + metrics | `/content/drive/MyDrive/DressApp_Gemma4_E2B_Training/Eyes_v4_run/` |

## Safety nets baked in

* Drive-resident checkpoints **every 100 steps** — a Colab disconnect at
  any point loses ≤ 100 steps of work, never the full run.
* `bf16` training on A100 (no quantization noise from QLoRA needed).
* **Vision tower frozen** — only the text decoder learns. Empirically
  what makes multimodal LoRAs stable on small corpora.
* Deterministic 80 / 10 / 10 train/val/test split keyed on filename
  hash, so re-running the notebook benches against the same held-out
  images every time.
* Post-train **bbox-IoU eval on the held-out test split**, computed
  in-notebook with the same metric as
  `/app/scripts/run_eyes_benchmark.py` — you can compare v4 vs v3
  head-to-head before quantizing.
"""

# ──────────────────────────────────────────────────────────────────────
# 2. Section 1 — Mount Drive + GPU sanity
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_DRIVE = """\
---

## 1. Mount Google Drive + GPU sanity check

Confirms the A100 is actually attached and both Drive folders exist
before we spend 20 min installing dependencies.
"""

CODE_MOUNT = """\
# Mount Drive at /content/drive
from google.colab import drive
drive.mount('/content/drive', force_remount=False)
"""

CODE_GPU = """\
# Verify A100 (or at least 24 GB+ VRAM). The notebook is sized for A100
# 40 GB; on smaller cards you'd need to drop ``per_device_train_batch_size``
# and probably enable 4-bit base loading via bitsandbytes (commented hooks
# in the training cell below).
!nvidia-smi
"""

CODE_PATHS = """\
import os, pathlib, sys

BASE_DIR     = pathlib.Path('/content/drive/MyDrive/DressApp_Gemma4_E2B_Training')
V3_MERGED    = BASE_DIR / 'Eyes_v3_Gemma4_E2B_merged'
V2_MMPROJ    = BASE_DIR / 'Eyes_v2_Gemma4e2b' / 'mmproj-Gemma4E2B-f16.gguf'
CCP_DIR      = pathlib.Path('/content/drive/MyDrive/ccp-DatasetNinja')
OUT_RUN_DIR  = BASE_DIR / 'Eyes_v4_run'                     # checkpoints + logs
OUT_MERGED   = BASE_DIR / 'Eyes_v4_Gemma4_E2B_merged'       # final fp16
OUT_GGUF     = BASE_DIR / 'Eyes_v4_Q4_K_M.gguf'             # final quant
OUT_RUN_DIR.mkdir(parents=True, exist_ok=True)

for p in (V3_MERGED, V2_MMPROJ, CCP_DIR):
    assert p.exists(), f'Missing input: {p}'
print('✅ All Drive paths reachable.')
print('   v3 base       :', V3_MERGED)
print('   mmproj (reuse):', V2_MMPROJ)
print('   ccp corpus    :', CCP_DIR)
print('   run dir       :', OUT_RUN_DIR)
"""

# ──────────────────────────────────────────────────────────────────────
# 3. Section 2 — Dependencies
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_DEPS = """\
---

## 2. Install pinned dependencies

We pin every library to a version we've actually tested together for
Gemma-3 multimodal LoRA on A100. Don't upgrade in place — newer
``transformers`` releases regularly break the Gemma-3 vision processor
keys (`pixel_values` vs `image_features` vs `pixel_values_videos`,
etc.). If anything fails downstream, the first debugging step is to
print the installed versions and compare against the pin block below.
"""

CODE_DEPS = """\
# Pinned versions known to work for Gemma-3 multimodal LoRA on A100
# (Colab Pro+, CUDA 12.x, May 2026). Update with care.
%pip install -q --upgrade pip
%pip install -q \\
    'transformers==4.50.0' \\
    'peft==0.13.2' \\
    'accelerate==1.0.1' \\
    'bitsandbytes==0.44.1' \\
    'datasets==3.1.0' \\
    'trl==0.12.0' \\
    'safetensors>=0.4.5' \\
    'sentencepiece>=0.2.0' \\
    'Pillow>=10.4.0' \\
    'numpy<2'

# Sanity print
import transformers, peft, accelerate, torch
print('torch       :', torch.__version__, 'cuda', torch.version.cuda)
print('transformers:', transformers.__version__)
print('peft        :', peft.__version__)
print('accelerate  :', accelerate.__version__)
print('bf16 ok?    :', torch.cuda.is_bf16_supported())
"""

# ──────────────────────────────────────────────────────────────────────
# 4. Section 3 — Load base + freeze vision tower
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_LOAD = """\
---

## 3. Load `Eyes_v3_Gemma4_E2B_merged`

We load in **bf16** (A100 native) with eager attention. The model class
is ``Gemma3ForConditionalGeneration`` — the multimodal variant that
wraps a SigLIP vision tower and a Gemma-3 text decoder via a learned
projector.

We then **freeze every parameter that lives in the vision tower or the
projector**. Only the text decoder participates in LoRA training. This
is the empirically-safe setting for small-corpus multimodal LoRA — the
vision encoder is far more sample-hungry than the text decoder and
will silently degrade if you let it train on 2 k images.
"""

CODE_LOAD_MODEL = """\
import torch
from transformers import (
    Gemma3ForConditionalGeneration, AutoProcessor,
)

model = Gemma3ForConditionalGeneration.from_pretrained(
    str(V3_MERGED),
    torch_dtype=torch.bfloat16,
    attn_implementation='eager',           # safest for Gemma-3 LoRA
    device_map={'': 0},                     # single GPU
)
processor = AutoProcessor.from_pretrained(str(V3_MERGED))

# Some processor configs ship without an explicit chat template; we
# override with the canonical Gemma-3 chat template so the same prompt
# at inference and training is bit-identical.
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

# Freeze vision tower + multimodal projector
vision_keys = ('vision_tower', 'multi_modal_projector', 'image_newline')
n_frozen = n_trainable = 0
for name, p in model.named_parameters():
    if any(k in name for k in vision_keys):
        p.requires_grad = False
        n_frozen += p.numel()
    else:
        n_trainable += p.numel()

print(f'Vision-side frozen params  : {n_frozen / 1e6:8.2f} M')
print(f'Text-side params (pre-LoRA): {n_trainable / 1e6:8.2f} M')
print(f'Total                       : {(n_frozen + n_trainable) / 1e9:6.2f} B')
"""

# ──────────────────────────────────────────────────────────────────────
# 5. Section 4 — CCP-DatasetNinja loader
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_DATASET = """\
---

## 4. CCP-DatasetNinja loader

DatasetNinja (Supervise.ly) format on disk:

```
ccp-DatasetNinja/
    meta.json                       # class palette
    ds/                             # 'dataset' subfolder
        img/
            0001.jpg
            0002.jpg
            ...
        ann/
            0001.jpg.json
            0002.jpg.json
            ...
```

Per-annotation JSON, each `objects[i]` carries:

* `classTitle`: e.g. `blouse`, `pants`, `shoes`, `skin`, `hair`, `null`
* `bitmap.data`: `base64( zlib( PNG_bytes ) )` — single-channel mask
* `bitmap.origin`: `[x, y]` offset of the mask top-left in image coords

We:

1. Decode the mask → enclosing pixel bbox
2. Skip non-garment classes (`skin`, `hair`, `null`)
3. Map CCP `classTitle` → DressApp category enum
   (`Top` / `Bottom` / `Outerwear` / `Full-body` / `Footwear` /
   `Accessory`)
4. Normalize the bbox to a `[ymin, xmin, ymax, xmax]` 0..1000 grid
   (the format Eyes already emits at inference — keeps the head's
   output distribution stable).
5. Build the target JSON array.
"""

CODE_DATASET_INSPECT = """\
import json, glob, collections
# Find the inner dataset folder — common layouts are `ds/`, `ds0/`,
# `train/`. We just walk for any directory containing `img/` + `ann/`.
def _find_dataset_root(base):
    for path in base.rglob('img'):
        if path.is_dir() and (path.parent / 'ann').is_dir():
            return path.parent
    raise FileNotFoundError(f'No `img/` + `ann/` pair found under {base}')

DS_ROOT = _find_dataset_root(CCP_DIR)
print('Dataset root:', DS_ROOT)

jpgs = sorted((DS_ROOT / 'img').glob('*.jpg'))
print(f'Total images: {len(jpgs)}')

# Quick class histogram on a 50-image sample so we can sanity-check the
# class map below before building the full loader.
sample = jpgs[: min(50, len(jpgs))]
counter = collections.Counter()
for j in sample:
    ann_path = DS_ROOT / 'ann' / f'{j.name}.json'
    if not ann_path.exists():
        continue
    d = json.loads(ann_path.read_text())
    for o in d.get('objects', []):
        counter[o['classTitle']] += 1
print('Top classes in first 50:')
for c, n in counter.most_common(15):
    print(f'  {c:18s} {n}')
"""

CODE_DATASET_MAP = """\
# Class-name → DressApp category. Anything *not* listed here is treated
# as non-garment and dropped from training labels.
CCP_TO_CATEGORY = {
    # Tops
    'blouse': 'Top', 'shirt': 'Top', 'sweater': 'Top', 't-shirt': 'Top',
    'tee': 'Top', 'tank': 'Top', 'top': 'Top', 'vest': 'Top',
    # Bottoms
    'pants': 'Bottom', 'skirt': 'Bottom', 'jeans': 'Bottom',
    'leggings': 'Bottom', 'shorts': 'Bottom',
    # Outerwear
    'coat': 'Outerwear', 'jacket': 'Outerwear', 'cape': 'Outerwear',
    'blazer': 'Outerwear',
    # Full-body
    'dress': 'Full-body', 'romper': 'Full-body', 'suit': 'Full-body',
    # Footwear
    'shoes': 'Footwear', 'boots': 'Footwear', 'heels': 'Footwear',
    'pumps': 'Footwear', 'sandals': 'Footwear', 'wedges': 'Footwear',
    'socks': 'Footwear', 'stockings': 'Footwear',
    # Accessories
    'bag': 'Accessory', 'purse': 'Accessory', 'wallet': 'Accessory',
    'belt': 'Accessory', 'necklace': 'Accessory', 'hat': 'Accessory',
    'sunglasses': 'Accessory', 'glasses': 'Accessory',
    'accessories': 'Accessory', 'scarf': 'Accessory', 'tie': 'Accessory',
    'gloves': 'Accessory',
}
# Explicit excludes (non-garment). Anything not in CCP_TO_CATEGORY and
# not in EXCLUDE is silently treated as 'unknown' and dropped.
EXCLUDE = {'skin', 'hair', 'null', ''}

print(f'Garment classes mapped: {len(CCP_TO_CATEGORY)}')
print(f'Excluded as non-garment: {sorted(EXCLUDE)}')
"""

CODE_DATASET_DECODE = """\
import base64, io, zlib
import numpy as np
from PIL import Image

def _decode_mask_bbox(bitmap_obj):
    \"\"\"Supervise.ly bitmap -> enclosing pixel bbox in full-image coords.

    Returns ``(x_min, y_min, x_max, y_max)`` or ``None`` if the mask is
    empty after decoding.
    \"\"\"
    raw = base64.b64decode(bitmap_obj['data'])
    try:
        inner = zlib.decompress(raw)
    except zlib.error:
        inner = raw                  # some exports omit the zlib layer
    arr = np.array(Image.open(io.BytesIO(inner)))
    if arr.ndim == 3:
        arr = arr.max(axis=2)
    ys, xs = np.nonzero(arr)
    if ys.size == 0:
        return None
    ox, oy = bitmap_obj['origin']
    return (int(ox + xs.min()), int(oy + ys.min()),
            int(ox + xs.max()), int(oy + ys.max()))


def _to_norm_bbox(bbox_px, img_w, img_h):
    \"\"\"Pixel ``(x1,y1,x2,y2)`` -> normalised ``[ymin, xmin, ymax, xmax]``
    on a 0..1000 grid (matches Eyes' production output schema).\"\"\"
    x1, y1, x2, y2 = bbox_px
    return [
        int(round(y1 / img_h * 1000)),
        int(round(x1 / img_w * 1000)),
        int(round(y2 / img_h * 1000)),
        int(round(x2 / img_w * 1000)),
    ]


def parse_one_image(jpg_path):
    \"\"\"Return ``(jpg_path, target_json_str)`` or ``None`` if no usable garments.\"\"\"
    ann_path = DS_ROOT / 'ann' / f'{jpg_path.name}.json'
    if not ann_path.exists():
        return None
    ann = json.loads(ann_path.read_text())
    img_w = int(ann.get('size', {}).get('width') or 0)
    img_h = int(ann.get('size', {}).get('height') or 0)
    if img_w <= 0 or img_h <= 0:
        with Image.open(jpg_path) as im:
            img_w, img_h = im.size
    items = []
    for obj in ann.get('objects', []):
        cls = (obj.get('classTitle') or '').lower().strip()
        if cls in EXCLUDE or cls not in CCP_TO_CATEGORY:
            continue
        if obj.get('geometryType') != 'bitmap':
            continue
        bbox = _decode_mask_bbox(obj['bitmap'])
        if bbox is None:
            continue
        items.append({
            'label': cls,
            'category': CCP_TO_CATEGORY[cls],
            'region': {'bbox': _to_norm_bbox(bbox, img_w, img_h)},
        })
    if not items:
        return None
    target = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    return (str(jpg_path), target)


# Build the full corpus list. Drops any image with zero usable garments
# (common for non-fashion photos that slipped into the CCP corpus).
all_records = []
for jpg in jpgs:
    rec = parse_one_image(jpg)
    if rec is not None:
        all_records.append(rec)
print(f'Usable training records: {len(all_records)} / {len(jpgs)}')
print('---')
print('Sample target JSON (image 0):')
print(all_records[0][1][:400])
"""

CODE_DATASET_SPLIT = """\
import hashlib, random

# Deterministic 80/10/10 split keyed on filename hash so the same image
# always falls into the same split, even if you re-run the notebook.
def _split_for(path: str):
    h = int(hashlib.sha256(path.encode()).hexdigest(), 16)
    r = h % 100
    if r < 80:  return 'train'
    if r < 90:  return 'val'
    return 'test'

train, val, test = [], [], []
for path, target in all_records:
    bucket = {'train': train, 'val': val, 'test': test}[_split_for(path)]
    bucket.append((path, target))
print(f'Splits:  train={len(train)}  val={len(val)}  test={len(test)}')
"""

# ──────────────────────────────────────────────────────────────────────
# 6. Section 5 — Conversation builder + collator
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_CONV = """\
---

## 5. Conversation template + masked-loss collator

We replicate the production prompt verbatim so that training and
inference see exactly the same surface form. Loss is computed **only
on the assistant turn** — we mask the user prompt by setting its
``labels`` to ``-100`` so gradients flow only through the JSON the
model is supposed to emit.
"""

CODE_PROMPT = """\
# Production system prompt — kept short and high-signal. Mirror this in
# /app/backend/app/services/garment_vision.py at inference time.
SYSTEM_PROMPT = (
    \"You are DressApp Eyes, a computer vision model specialised in clothing.\\n\"
    \"You receive ONE photograph and you return ONLY valid JSON.\\n\"
    \"\\n\"
    \"Schema: a JSON array. Each element describes ONE distinct visible\\n\"
    \"garment, accessory, or footwear item:\\n\"
    \"  { \\\"label\\\":    string,                          // CCP class title\\n\"
    \"    \\\"category\\\": one of [Top|Bottom|Outerwear|Full-body|Footwear|Accessory],\\n\"
    \"    \\\"region\\\":   { \\\"bbox\\\": [ymin, xmin, ymax, xmax] } // 0..1000 grid\\n\"
    \"  }\\n\"
    \"\\n\"
    \"Rules:\\n\"
    \" - Always return an array. A single-item photo returns a one-element array.\\n\"
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
    \"\"\"Turn one (image_path, target_json) record into a model-ready tensor dict.

    We tokenise the full conversation once with ``add_generation_prompt=False``,
    then re-tokenise just the prompt-side (no assistant turn) to know where
    the assistant starts. Everything before the assistant turn is masked
    out of the loss with ``-100``.
    \"\"\"
    img_path, target_json = record
    image = _PIL_Image.open(img_path).convert('RGB')

    messages_full = [
        {'role': 'user', 'content': [
            {'type': 'image'},
            {'type': 'text', 'text': SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
        ]},
        {'role': 'model', 'content': [{'type': 'text', 'text': target_json}]},
    ]
    messages_prompt = messages_full[:1]   # user-only

    # `apply_chat_template` returns the string for both branches — we
    # pass both through the processor so we get aligned image+text tensors.
    full_text   = processor.apply_chat_template(messages_full,   add_generation_prompt=False, tokenize=False)
    prompt_text = processor.apply_chat_template(messages_prompt, add_generation_prompt=True,  tokenize=False)

    full   = processor(text=full_text,   images=image, return_tensors='pt', padding=False)
    prompt = processor(text=prompt_text, images=image, return_tensors='pt', padding=False)

    input_ids = full['input_ids'][0]
    labels    = input_ids.clone()
    n_prompt  = prompt['input_ids'].shape[1]
    labels[:n_prompt] = ignore_index

    out = {
        'input_ids':       input_ids,
        'attention_mask':  full['attention_mask'][0],
        'labels':          labels,
        'pixel_values':    full['pixel_values'][0],
    }
    if 'token_type_ids' in full:
        out['token_type_ids'] = full['token_type_ids'][0]
    return out


# Smoke-test one record so we catch any processor mismatch before
# burning 30 min on training.
ex = build_example(train[0])
for k, v in ex.items():
    print(f'  {k:18s} shape={tuple(v.shape)} dtype={v.dtype}')
print(f'  loss-active tokens : {(ex[\"labels\"] != -100).sum().item()}')
"""

CODE_COLLATOR = """\
from dataclasses import dataclass

@dataclass
class GemmaVLCollator:
    \"\"\"Pads variable-length input_ids / labels / attention_mask, stacks pixel_values.

    Gemma-3 multimodal samples have one image apiece (and a fixed-size
    pixel_values tensor after the processor), so we can naively
    ``torch.stack`` them. The text tensors vary by length and need
    right-padding.
    \"\"\"
    pad_token_id: int
    ignore_index: int = -100

    def __call__(self, batch):
        max_len = max(len(b['input_ids']) for b in batch)
        out = {
            'input_ids':       [], 'attention_mask': [],
            'labels':          [], 'pixel_values':   [],
        }
        for b in batch:
            n_pad = max_len - len(b['input_ids'])
            out['input_ids'].append(
                torch.cat([b['input_ids'],
                           torch.full((n_pad,), self.pad_token_id, dtype=b['input_ids'].dtype)])
            )
            out['attention_mask'].append(
                torch.cat([b['attention_mask'],
                           torch.zeros(n_pad, dtype=b['attention_mask'].dtype)])
            )
            out['labels'].append(
                torch.cat([b['labels'],
                           torch.full((n_pad,), self.ignore_index, dtype=b['labels'].dtype)])
            )
            out['pixel_values'].append(b['pixel_values'])
        return {
            'input_ids':      torch.stack(out['input_ids']),
            'attention_mask': torch.stack(out['attention_mask']),
            'labels':         torch.stack(out['labels']),
            'pixel_values':   torch.stack(out['pixel_values']),
        }

collator = GemmaVLCollator(pad_token_id=processor.tokenizer.pad_token_id)
print('Collator ready. pad_id =', collator.pad_token_id)
"""

CODE_DATASET_CLASS = """\
from torch.utils.data import Dataset

class CcpRecordDataset(Dataset):
    \"\"\"Thin Dataset wrapping (img_path, target_json) records — examples are
    built lazily so we don't decode 2000 JPEGs into RAM at startup.\"\"\"

    def __init__(self, records):
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, i):
        return build_example(self.records[i])

train_ds = CcpRecordDataset(train)
val_ds   = CcpRecordDataset(val)
test_ds  = CcpRecordDataset(test)
print(f'train: {len(train_ds)}   val: {len(val_ds)}   test: {len(test_ds)}')
"""

# ──────────────────────────────────────────────────────────────────────
# 7. Section 6 — LoRA setup
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_LORA = """\
---

## 6. LoRA adapter (text-decoder only)

Targets the attention + MLP projections of every transformer block in
the text decoder. We leave the vision tower frozen via the
``modules_to_save=None`` + the ``requires_grad=False`` we set above —
PEFT only injects into modules it can see in the target list, and our
target list explicitly names text-decoder Linear modules.

| Hyperparameter | Value | Why |
| --- | --- | --- |
| `r` | 16 | Small enough to add ~30 M params, large enough to capture multi-garment routing. |
| `lora_alpha` | 32 | `2× r`, the long-standing safe ratio. |
| `lora_dropout` | 0.05 | Light regularisation given the small-ish corpus. |
| `target_modules` | attn + MLP linears | Standard Gemma-3 LoRA recipe. |
| `bias` | `'none'` | Doesn't help with this objective; saves params. |
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
        'q_proj', 'k_proj', 'v_proj', 'o_proj',           # attention
        'gate_proj', 'up_proj', 'down_proj',              # MLP
    ],
)

model = get_peft_model(model, lora_cfg)
model.print_trainable_parameters()                        # expect <1 %
"""

# ──────────────────────────────────────────────────────────────────────
# 8. Section 7 — Training
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_TRAIN = """\
---

## 7. Train

A100 + bf16 → no QLoRA needed, batch 4 fits comfortably with
grad-accum 4 (effective batch 16). ~1600 train examples ÷ 16 ≈ 100
optimizer steps per epoch · 3 epochs ≈ **300 total steps**. Plan for
roughly **20–30 minutes** wall.

A checkpoint is written to Drive every 100 steps, so a Colab
disconnect at the worst possible moment costs you a few minutes of
re-train, not the entire run.
"""

CODE_TRAINING_ARGS = """\
from transformers import TrainingArguments, Trainer

args = TrainingArguments(
    output_dir=str(OUT_RUN_DIR),
    overwrite_output_dir=True,

    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,                 # effective batch 16
    per_device_eval_batch_size=4,

    bf16=True,
    gradient_checkpointing=True,
    optim='adamw_torch_fused',
    learning_rate=2e-4,
    lr_scheduler_type='cosine',
    warmup_ratio=0.03,
    weight_decay=0.01,
    max_grad_norm=1.0,

    logging_steps=10,
    save_strategy='steps',
    save_steps=100,
    save_total_limit=3,
    eval_strategy='steps',
    eval_steps=100,
    load_best_model_at_end=True,
    metric_for_best_model='eval_loss',
    greater_is_better=False,

    report_to='none',
    remove_unused_columns=False,
    dataloader_num_workers=2,
    dataloader_pin_memory=True,
    seed=42,
)
print('TrainingArguments configured.')
"""

CODE_TRAIN = """\
trainer = Trainer(
    model=model,
    args=args,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    data_collator=collator,
)
trainer.train()
"""

# ──────────────────────────────────────────────────────────────────────
# 9. Section 8 — Eval (bbox IoU)
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_EVAL = """\
---

## 8. Eval — bbox IoU on the held-out test split

Mirrors the in-pod metric in ``/app/scripts/run_eyes_benchmark.py`` so
v4 numbers are directly comparable with the v3 results recorded
in chat:

| Run | mean IoU | recall @0.5 | precision @0.5 |
| --- | ---: | ---: | ---: |
| **v3 — one-pass (Gemini Flash, no fine-tune)** | 0.49 | 0.10 | 0.53 |
| **v3 — legacy SegFormer + per-crop Eyes** | 0.74 | 0.56 | 0.78 |
| **v4 — fine-tuned one-pass** *(this run)* | ? | ? | ? |

The cell below puts the model in eval mode, generates JSON for each
test image with constrained decoding (low temperature, ``max_new_tokens``
budget sized for ~10 garments), parses it, and computes the same
greedy max-IoU matching the in-pod benchmark uses.
"""

CODE_EVAL = """\
import re, time

model.eval()

def _safe_parse(text):
    \"\"\"Extract the first JSON array we can find in ``text`` and parse it.

    LoRA-trained models occasionally emit a stray prefix / suffix
    despite the JSON-only prompt; we tolerate it by isolating
    everything between the first '[' and the matching ']'.
    \"\"\"
    m = re.search(r'\\[.*\\]', text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _iou(a, b):
    \"\"\"(x1,y1,x2,y2) bboxes -> IoU.\"\"\"
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = max(0, ax2 - ax1) * max(0, ay2 - ay1) + max(0, bx2 - bx1) * max(0, by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def _denorm(bbox_norm, w, h):
    ymin, xmin, ymax, xmax = bbox_norm
    return (int(xmin / 1000 * w), int(ymin / 1000 * h),
            int(xmax / 1000 * w), int(ymax / 1000 * h))


def _predict(img_path):
    image = _PIL_Image.open(img_path).convert('RGB')
    msgs = [{'role': 'user', 'content': [
        {'type': 'image'},
        {'type': 'text', 'text': SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
    ]}]
    text = processor.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    enc = processor(text=text, images=image, return_tensors='pt', padding=False).to(model.device)
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=512,
            do_sample=False,
            temperature=0.0,
            pad_token_id=processor.tokenizer.pad_token_id,
        )
    decoded = processor.tokenizer.decode(out[0][enc['input_ids'].shape[1]:], skip_special_tokens=True)
    return _safe_parse(decoded), decoded


# Run on the test split
import numpy as np
per_image_ious = []
n_gt = n_pred = n_matched_05 = 0
t0 = time.perf_counter()

for img_path, target_json in test_ds.records:
    gts_norm = json.loads(target_json)
    with _PIL_Image.open(img_path) as im:
        w, h = im.size
    gts_px = [_denorm(g['region']['bbox'], w, h) for g in gts_norm]
    preds, raw = _predict(img_path)
    if not isinstance(preds, list):
        n_gt += len(gts_px)
        continue
    preds_px = []
    for p in preds:
        bb = (p.get('region') or {}).get('bbox')
        if isinstance(bb, list) and len(bb) == 4:
            preds_px.append(_denorm(bb, w, h))
    # greedy max-IoU matching (same as benchmark script)
    triples = sorted(
        [(_iou(pp, gg), pi, gi) for pi, pp in enumerate(preds_px) for gi, gg in enumerate(gts_px)],
        reverse=True,
    )
    used_p, used_g = set(), set()
    for iou, pi, gi in triples:
        if pi in used_p or gi in used_g:
            continue
        used_p.add(pi); used_g.add(gi)
        per_image_ious.append(iou)
        if iou >= 0.5:
            n_matched_05 += 1
    n_gt   += len(gts_px)
    n_pred += len(preds_px)

elapsed = time.perf_counter() - t0
mean_iou = float(np.mean(per_image_ious)) if per_image_ious else 0.0
print(f'tested {len(test_ds.records)} imgs in {elapsed:.1f}s')
print(f'  mean IoU              : {mean_iou:.3f}')
print(f'  recall @ IoU=0.5      : {n_matched_05 / n_gt:.3f}' if n_gt else '  no GT')
print(f'  precision @ IoU=0.5   : {n_matched_05 / n_pred:.3f}' if n_pred else '  no predictions')
print(f'  avg pred per image    : {n_pred / len(test_ds.records):.2f}')
"""

# ──────────────────────────────────────────────────────────────────────
# 10. Section 9 — Merge + save
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_MERGE = """\
---

## 9. Merge LoRA + save fp16 to Drive

`peft.merge_and_unload()` writes the LoRA deltas back into the base
weights and returns a plain ``Gemma3ForConditionalGeneration``.
That's the artifact we'll quantize next; it's also a perfectly valid
training base for a hypothetical v5.
"""

CODE_MERGE = """\
merged = model.merge_and_unload()
OUT_MERGED.mkdir(parents=True, exist_ok=True)

merged.save_pretrained(str(OUT_MERGED), safe_serialization=True, max_shard_size='4GB')
processor.save_pretrained(str(OUT_MERGED))

import os
total_gb = sum(p.stat().st_size for p in OUT_MERGED.rglob('*')) / (1024**3)
print(f'✅ Saved merged fp16 to {OUT_MERGED}  ({total_gb:.2f} GB)')
"""

# ──────────────────────────────────────────────────────────────────────
# 11. Section 10 — Quantize to GGUF
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_QUANT = """\
---

## 10. Convert to GGUF + quantize to Q4_K_M

We clone `llama.cpp`, build it once, then run their
``convert_hf_to_gguf.py`` to produce an fp16 GGUF and finally
``llama-quantize`` to compress it to Q4_K_M (the same recipe your
`phase6-Q4_K_M.gguf` artifact used).

The **vision tower is unchanged** (frozen during LoRA), so we do NOT
re-export the multimodal projector. The existing
`mmproj-Gemma4E2B-f16.gguf` from v2 ships unchanged alongside the new
text GGUF.
"""

CODE_GGUF_CLONE = """\
!cd /content && \\
    [ -d llama.cpp ] || git clone --depth 1 https://github.com/ggerganov/llama.cpp llama.cpp
%cd /content/llama.cpp
!pip install -q -r requirements/requirements-convert_hf_to_gguf.txt
!cmake -B build -DGGML_CUDA=ON 2>&1 | tail -5
!cmake --build build --config Release --target llama-quantize -j 2>&1 | tail -5
"""

CODE_GGUF_CONVERT = """\
F16_GGUF = OUT_RUN_DIR / 'Eyes_v4-f16.gguf'

# Convert the merged HF folder to an fp16 GGUF
!python /content/llama.cpp/convert_hf_to_gguf.py \\
    {OUT_MERGED} \\
    --outtype f16 \\
    --outfile {F16_GGUF}

print('fp16 GGUF size:', round(F16_GGUF.stat().st_size / 1024 ** 3, 2), 'GB')
"""

CODE_GGUF_QUANT = """\
# Quantize to Q4_K_M (matches your phase6 recipe).
!/content/llama.cpp/build/bin/llama-quantize \\
    {F16_GGUF} \\
    {OUT_GGUF} \\
    Q4_K_M

print('Q4_K_M GGUF size:', round(OUT_GGUF.stat().st_size / 1024 ** 3, 2), 'GB')
print('mmproj (reused) :', V2_MMPROJ)

# Optional: delete the fp16 intermediate from Drive to save space
# F16_GGUF.unlink()
"""

# ──────────────────────────────────────────────────────────────────────
# 12. Section 11 — Sanity probe via llama-cpp-python
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_PROBE = """\
---

## 11. End-to-end sanity probe via `llama-cpp-python`

Loads the *new* Q4_K_M alongside the *unchanged* mmproj and runs Eyes
on 5 random test images — same code path the Hetzner container will
use. Confirms that:

1. The new GGUF actually loads with the v2 mmproj (no projector
   incompatibility from the fine-tune).
2. The model emits valid JSON (no LoRA-induced output drift).
3. The output IS a multi-garment array on outfit photos
   (the whole point of this notebook).
"""

CODE_PROBE_INSTALL = """\
# CUDA build of llama-cpp-python so the probe runs on the A100.
%pip install -q --upgrade \\
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 \\
    'llama-cpp-python==0.3.2'
"""

CODE_PROBE_RUN = """\
import random
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Gemma3ChatHandler

handler = Gemma3ChatHandler(clip_model_path=str(V2_MMPROJ))
llm = Llama(
    model_path=str(OUT_GGUF),
    chat_handler=handler,
    n_ctx=4096,
    n_gpu_layers=-1,
    verbose=False,
)

random.seed(42)
samples = random.sample(test_ds.records, k=min(5, len(test_ds.records)))

for img_path, target_json in samples:
    print('═' * 70)
    print('Image :', os.path.basename(img_path))
    resp = llm.create_chat_completion(
        messages=[
            {'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': f'file://{img_path}'}},
                {'type': 'text', 'text': SYSTEM_PROMPT + '\\n\\n' + USER_INSTRUCTION},
            ]},
        ],
        temperature=0.0,
        max_tokens=512,
    )
    raw = resp['choices'][0]['message']['content']
    parsed = _safe_parse(raw)
    print('Predicted garments (parsed):', json.dumps(parsed, indent=2) if parsed else f'  [unparseable]\\n  raw={raw[:200]}')
    print('Ground truth          :', json.dumps(json.loads(target_json), indent=2))
"""

# ──────────────────────────────────────────────────────────────────────
# 13. Done
# ──────────────────────────────────────────────────────────────────────
MD_SECTION_DONE = """\
---

## ✅ Done — deployment hand-off

On the **Hetzner inference pod**:

1. `scp` the new artifact to the pod:
   * `Eyes_v4_Q4_K_M.gguf`  →  the model
   * `mmproj-Gemma4E2B-f16.gguf`  →  unchanged from v2
2. Restart the `dressapp-eyes` container.
3. **Re-run the in-pod benchmark** against the same 30-image
   `test_images` slice to confirm the metrics you saw in section 8 hold
   end-to-end through the FastAPI bridge:

   ```bash
   /root/.venv/bin/python /app/scripts/run_eyes_benchmark.py \\
       --analyzer=one_pass --limit=30
   ```

4. If recall @0.5 ≥ 0.8 holds → it's time to **un-retire**
   `EYES_ONE_PASS=true` on Hetzner and ship the faster, simpler
   single-call path back into production.

If the headline number didn't move, the most likely culprit is
**under-training**: bump `num_train_epochs` to 5, re-merge, re-quantize,
re-probe. We've sized the checkpoint cadence so an extra two epochs is
~15 min, not "rerun the whole notebook."
"""


# ──────────────────────────────────────────────────────────────────────
# Assemble the notebook
# ──────────────────────────────────────────────────────────────────────
CELLS = [
    md(MD_TITLE),

    md(MD_SECTION_DRIVE),
    code(CODE_MOUNT),
    code(CODE_GPU),
    code(CODE_PATHS),

    md(MD_SECTION_DEPS),
    code(CODE_DEPS),

    md(MD_SECTION_LOAD),
    code(CODE_LOAD_MODEL),

    md(MD_SECTION_DATASET),
    code(CODE_DATASET_INSPECT),
    code(CODE_DATASET_MAP),
    code(CODE_DATASET_DECODE),
    code(CODE_DATASET_SPLIT),

    md(MD_SECTION_CONV),
    code(CODE_PROMPT),
    code(CODE_BUILD_EXAMPLE),
    code(CODE_COLLATOR),
    code(CODE_DATASET_CLASS),

    md(MD_SECTION_LORA),
    code(CODE_LORA),

    md(MD_SECTION_TRAIN),
    code(CODE_TRAINING_ARGS),
    code(CODE_TRAIN),

    md(MD_SECTION_EVAL),
    code(CODE_EVAL),

    md(MD_SECTION_MERGE),
    code(CODE_MERGE),

    md(MD_SECTION_QUANT),
    code(CODE_GGUF_CLONE),
    code(CODE_GGUF_CONVERT),
    code(CODE_GGUF_QUANT),

    md(MD_SECTION_PROBE),
    code(CODE_PROBE_INSTALL),
    code(CODE_PROBE_RUN),

    md(MD_SECTION_DONE),
]

NB = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (Colab)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.10"},
        "accelerator": "GPU",
        "colab": {"gpuClass": "premium", "provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(NB, indent=1) + "\n")
print(f"Wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB, {len(CELLS)} cells)")
