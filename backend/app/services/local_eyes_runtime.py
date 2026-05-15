"""Eyes v4 — local one-pass garment analyzer.

Runs the user's fine-tuned ``google/gemma-4-E2B-it`` + LoRA adapter
directly in-process via ``transformers`` + ``peft``. The adapter was
trained on CCP-DatasetNinja + DeepFashion-Multimodal in
``/app/docs/notebooks/Eyes_FineTune_v4_Gemma4.ipynb``.

Activated by ``EYES_LOCAL=true`` in ``backend/.env``. When the flag is
on, ``/closet/analyze`` routes its multi-garment branch through this
module instead of the SegFormer + per-crop pipeline; on **any** error
(model load failure, OOM, JSON parse failure, missing adapter dir on
the lightweight Emergent pod, ...) the route falls back transparently
to the SegFormer pipeline so the user never sees a hard failure.

This file deliberately does NOT import torch / transformers / peft at
module load time. Heavy imports happen inside :func:`_init_sync`,
guarded by an asyncio lock and a one-shot ``_init_failed`` latch.
That keeps the lightweight pod (where torch isn't even installed) from
crashing on backend startup.

Output shape matches :func:`garment_vision.GarmentVisionService.analyze_outfit_one_pass`
exactly so the closet API contract is unchanged.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Configuration via environment ──────────────────────────────────
# All of these have sensible defaults; only ``EYES_LOCAL=true`` is
# strictly required to switch the route on. Override the others when
# the on-disk layout on Hetzner differs (e.g. you store the adapter at
# ``/var/lib/dressapp/eyes_v4_adapter`` instead of ``/srv/eyes/...``).

EYES_LOCAL_BASE_MODEL = os.environ.get(
    "EYES_LOCAL_BASE_MODEL", "google/gemma-4-E2B-it"
)
EYES_LOCAL_ADAPTER_DIR = os.environ.get(
    "EYES_LOCAL_ADAPTER_DIR", "/srv/AI-Stylist/eyes_v4_adapter"
)
# Optional dir containing SYSTEM_PROMPT.txt + USER_INSTRUCTION.txt
# (the Colab notebook saves these alongside the adapter). When the
# files are absent or unreadable we fall back to baked-in defaults so
# the runtime works even if only the adapter weights got copied over.
EYES_LOCAL_PROMPTS_DIR = os.environ.get(
    "EYES_LOCAL_PROMPTS_DIR", "/srv/AI-Stylist/eyes_v4_adapter"
)
EYES_LOCAL_MAX_NEW_TOKENS = int(os.environ.get("EYES_LOCAL_MAX_NEW_TOKENS", "256"))
# ``device_map`` for HF ``from_pretrained``. ``"auto"`` uses every GPU
# the box has; set to ``{"": 0}`` to pin to GPU 0 if you're sharing
# the host with another model.
EYES_LOCAL_DEVICE_MAP = os.environ.get("EYES_LOCAL_DEVICE_MAP", "auto")


# ─── Module singletons (lazy init) ──────────────────────────────────
_runtime: dict[str, Any] | None = None
_init_lock = asyncio.Lock()
_init_failed: bool = False


# Defaults mirror the prompts the notebook used during training.
# Kept here verbatim so a brand-new Hetzner deploy that hasn't yet
# scp'd the prompt files still produces the same tokens the LoRA was
# trained against.
_DEFAULT_SYSTEM_PROMPT = (
    "You are DressApp Eyes, a vision model specialised in clothing.\n"
    "You receive ONE photograph and return ONLY valid JSON.\n\n"
    "Schema: a JSON array. Each element describes ONE distinct visible\n"
    "garment, accessory, or footwear item:\n"
    "  { \"label\":    string,\n"
    "    \"category\": one of [Top|Bottom|Outerwear|Full-body|Footwear|Accessory],\n"
    "    \"region\":   { \"bbox\": [ymin, xmin, ymax, xmax] }  // 0..1000 grid\n"
    "  }\n\n"
    "Rules:\n"
    " - Always return an array. A single-garment photo returns a one-element array.\n"
    " - List EVERY distinct garment. Layered outfits = N elements.\n"
    " - Skip skin, hair, body parts, backgrounds.\n"
    " - bbox values are integers on a 0..1000 grid, NOT pixels.\n"
    " - No prose, no markdown - JSON only.\n"
)
_DEFAULT_USER_INSTRUCTION = (
    "Analyze this outfit photograph and return the JSON array."
)

_VALID_CATEGORIES = {
    "Top", "Bottom", "Outerwear", "Full-body", "Footwear", "Accessory",
}


def _read_text_or(path: Path, fallback: str) -> str:
    try:
        text = path.read_text().strip()
        return text or fallback
    except Exception:
        return fallback


# ─── One-time heavyweight init ──────────────────────────────────────
def _init_sync() -> dict[str, Any]:
    """Load processor, base model, apply LoRA, merge.

    Synchronous; called from inside :func:`_init` via
    :func:`asyncio.to_thread` so the FastAPI event loop stays
    responsive while the ~5 GB checkpoint downloads/loads. Raises on
    any failure; caller traps and disables the runtime permanently
    for the rest of the process lifetime so retries don't hammer the
    GPU on every analyze request.
    """
    import torch  # noqa: PLC0415
    from peft import PeftModel  # noqa: PLC0415
    from transformers import AutoModelForMultimodalLM, AutoProcessor  # noqa: PLC0415

    adapter_dir = Path(EYES_LOCAL_ADAPTER_DIR)
    if not adapter_dir.is_dir():
        raise RuntimeError(
            f"Eyes adapter not found at {adapter_dir!s}. Set "
            "EYES_LOCAL_ADAPTER_DIR or copy the trained adapter from "
            "the training Drive (it lives at "
            "DressApp_Gemma4_E2B_Training/eyes_v4_adapter)."
        )

    t0 = time.perf_counter()
    logger.info("Eyes local: loading processor for %s", EYES_LOCAL_BASE_MODEL)
    processor = AutoProcessor.from_pretrained(EYES_LOCAL_BASE_MODEL)

    logger.info(
        "Eyes local: loading base model %s (dtype=bf16, device_map=%s)",
        EYES_LOCAL_BASE_MODEL,
        EYES_LOCAL_DEVICE_MAP,
    )
    base = AutoModelForMultimodalLM.from_pretrained(
        EYES_LOCAL_BASE_MODEL,
        dtype=torch.bfloat16,
        device_map=EYES_LOCAL_DEVICE_MAP,
        attn_implementation="eager",
    )

    logger.info("Eyes local: applying LoRA from %s", adapter_dir)
    model = PeftModel.from_pretrained(base, str(adapter_dir))
    # ``merge_and_unload`` bakes the adapter into the base linears so
    # subsequent forward passes have zero PEFT overhead. PEFT bug #3025
    # is fixed in ≥0.13; on older versions you'll see the AttributeError
    # at the end of merge — let it propagate, init_failed will latch
    # and the route will fall back cleanly.
    model = model.merge_and_unload()
    model.eval()

    prompts_dir = Path(EYES_LOCAL_PROMPTS_DIR)
    system_prompt = _read_text_or(
        prompts_dir / "SYSTEM_PROMPT.txt", _DEFAULT_SYSTEM_PROMPT,
    )
    user_instruction = _read_text_or(
        prompts_dir / "USER_INSTRUCTION.txt", _DEFAULT_USER_INSTRUCTION,
    )
    if system_prompt is _DEFAULT_SYSTEM_PROMPT:
        logger.info("Eyes local: using baked-in default SYSTEM_PROMPT")
    if user_instruction is _DEFAULT_USER_INSTRUCTION:
        logger.info("Eyes local: using baked-in default USER_INSTRUCTION")

    elapsed = time.perf_counter() - t0
    logger.info("Eyes local ready in %.1fs", elapsed)
    return {
        "model": model,
        "processor": processor,
        "system_prompt": system_prompt,
        "user_instruction": user_instruction,
    }


async def _init() -> dict[str, Any] | None:
    """Idempotent async init. Returns the runtime dict or ``None`` if
    init has previously failed (logged once on first failure).
    """
    global _runtime, _init_failed
    if _runtime is not None:
        return _runtime
    if _init_failed:
        return None

    async with _init_lock:
        if _runtime is not None:
            return _runtime
        if _init_failed:
            return None
        try:
            _runtime = await asyncio.to_thread(_init_sync)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Eyes local init FAILED (%r) — falling back to legacy "
                "pipeline. Set EYES_LOCAL=false to silence this on "
                "boxes without GPU.",
                exc,
            )
            _init_failed = True
            return None
    return _runtime


# ─── Inference ──────────────────────────────────────────────────────
def _safe_parse_json_array(text: str) -> Any:
    """Tolerant JSON-array extractor — copes with trailing markdown,
    leading thinking traces, etc. Returns ``None`` when nothing
    array-like is present."""
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _generate_sync(rt: dict[str, Any], image_bytes: bytes) -> str:
    """Run a single forward + decode. Sync; called via
    :func:`asyncio.to_thread` from :func:`analyze`. Pulls ``torch`` /
    ``PIL`` lazily so this module's mere import is still cheap on
    the lightweight pod that doesn't have torch installed."""
    import torch  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    msgs = [
        {"role": "system", "content": rt["system_prompt"]},
        {"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": rt["user_instruction"]},
        ]},
    ]
    processor = rt["processor"]
    model = rt["model"]

    # Two-step: render template to text, then call processor with
    # text + images explicitly. ``apply_chat_template(tokenize=True)``
    # does NOT reliably extract inline PIL images from the chat-message
    # content list on the current Gemma-4 release, which would silently
    # drop ``image_position_ids`` from the model inputs and crash the
    # SigLIP gate. Mirror the pattern the training notebook uses.
    text = processor.apply_chat_template(
        msgs,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    enc = processor(
        text=text, images=image, return_tensors="pt",
    ).to(model.device)
    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=EYES_LOCAL_MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=processor.tokenizer.pad_token_id,
        )
    return processor.tokenizer.decode(
        out[0][enc["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )


async def analyze(
    image_bytes: bytes,
    *,
    language: str | None = None,  # noqa: ARG001 — accepted for parity
    max_items: int = 6,
) -> list[dict[str, Any]]:
    """Run Eyes v4 on ``image_bytes`` and return per-garment items in
    the same shape as
    ``GarmentVisionService.analyze_outfit_one_pass``.

    Returns ``[]`` (never raises) on any soft failure so callers can
    fall back to the SegFormer pipeline transparently.
    """
    rt = await _init()
    if rt is None:
        return []

    t0 = time.perf_counter()
    try:
        raw_text = await asyncio.to_thread(_generate_sync, rt, image_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Eyes local generate failed: %r", exc)
        return []

    parsed = _safe_parse_json_array(raw_text)
    if not isinstance(parsed, list):
        logger.warning(
            "Eyes local returned non-array (head=%r) — falling back",
            (raw_text or "")[:200],
        )
        return []

    if max_items and len(parsed) > max_items:
        logger.info(
            "Eyes local: trimming %d garments to max_items=%d",
            len(parsed), max_items,
        )
        parsed = parsed[:max_items]

    # Lazy import — keeps this module loadable on lightweight pods
    # where garment_vision's heavy LLM SDKs aren't installed either.
    from app.services.garment_vision import _crop_to_bbox  # noqa: PLC0415

    items: list[dict[str, Any]] = []
    for g in parsed:
        if not isinstance(g, dict):
            continue
        label = (str(g.get("label") or "").strip() or "garment")
        category_raw = str(g.get("category") or "").strip()
        category = category_raw if category_raw in _VALID_CATEGORIES else ""

        # bbox normalisation — same defensive clamp used by
        # analyze_outfit_one_pass.
        region = g.get("region") if isinstance(g.get("region"), dict) else {}
        bbox_in = region.get("bbox") if isinstance(region.get("bbox"), list) else None

        is_full_frame = False
        bbox: list[int]
        if isinstance(bbox_in, list) and len(bbox_in) == 4:
            try:
                ymin, xmin, ymax, xmax = (
                    max(0, min(1000, int(v))) for v in bbox_in
                )
                if ymax <= ymin:
                    ymax = min(1000, ymin + 1)
                if xmax <= xmin:
                    xmax = min(1000, xmin + 1)
                bbox = [ymin, xmin, ymax, xmax]
            except Exception:
                bbox = [0, 0, 1000, 1000]
                is_full_frame = True
        else:
            bbox = [0, 0, 1000, 1000]
            is_full_frame = True

        if bbox == [0, 0, 1000, 1000]:
            is_full_frame = True

        # Crop using the same helper the legacy pipeline uses, so
        # padding / min-area floor rules stay consistent.
        if is_full_frame:
            crop_bytes = image_bytes
        else:
            cropped = _crop_to_bbox(image_bytes, bbox)
            crop_bytes = cropped[0] if cropped else image_bytes

        # Eyes v4 was trained to emit only {label, category, region}.
        # The wider GarmentAnalysis schema (color, fabric, condition…)
        # is left empty — the closet card renders fine with these
        # fields missing and the user can refine on the item-detail
        # screen. Future Eyes phases will widen the output.
        analysis: dict[str, Any] = {
            "item_type": label,
            "sub_category": label,
        }
        if category:
            analysis["category"] = category

        items.append({
            "label": label,
            "kind": "garment",
            "bbox": bbox,
            "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
            "crop_mime": "image/jpeg",
            "analysis": analysis,
            # Hint the frontend to show the "Repair photo" CTA when
            # we cropped out of a busy multi-item frame.
            "reconstruction_advised": not is_full_frame,
            # Debug breadcrumb — set to True on every Eyes-v4 item so
            # the diagnostic notebook can tell apart legacy vs local
            # routes by inspecting the response.
            "one_pass": True,
        })

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Eyes local OK garments=%d elapsed_ms=%d labels=%s",
        len(items), elapsed_ms, [i["label"] for i in items][:8],
    )
    return items


def runtime_loaded() -> bool:
    """Cheap probe — True iff init has succeeded at least once."""
    return _runtime is not None


def runtime_failed() -> bool:
    """Cheap probe — True iff init has failed and is permanently
    disabled for the rest of this process."""
    return _init_failed
