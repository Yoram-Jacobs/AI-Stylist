"""The Eyes — multimodal garment analyzer.

Production architecture (Phase O.3+)
------------------------------------
* Primary analyser: self-hosted **Gemma 4 E2B** GGUF served by the
  ``dressapp-eyes`` container (llama.cpp/llama-server). The backend
  reaches it via ``EYES_GEMMA_SPACE_URL`` — on Hetzner production
  this is ``http://eyes:7860`` (internal Docker network).
* Bounding-box detector for the multi-item pipeline:
  **SegFormer-b3** (sayeed99/segformer_b3_clothes) running LOCALLY
  in-process via ``app.services.clothing_parser``. No external call.
* Safety fallback when the Gemma container is unreachable:
  **Gemini 2.5 Flash** via Emergent / direct Google chat key. Tagged
  in the response with ``provider_fallback`` so the UI can surface
  the degraded state.
* Enum sanitiser, NMS, "already cropped" short-circuit, multi-item
  orchestration are all provider-agnostic and wrap either path.

Deprecated paths (removed in May 2026)
--------------------------------------
* Qwen-VL-Plus Eyes via HuggingFace Inference Providers
  (``_hf_chat_json`` + ``_hf_client`` + ``QWEN_EYES_MODEL`` setting).
  Never enabled in production; deleted along with the rest of the
  DashScope / Qwen integration. The DB-backed override layer
  (``eyes_override``) already rejects ``"qwen"`` at ``_VALID_PROVIDERS``
  so any stale persisted override falls through to env-default.
* DashScope Qwen-VL stylist brain (``QwenStylistBrain`` +
  ``qwen_client``). Removed alongside the Eyes path — see
  ``docs/WASTED_WORK_REPORT.md §2.2``.
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
import uuid
from typing import Any

from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
from PIL import Image

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)


async def _call_gemma_space(
    *,
    system_prompt: str,
    user_text: str,
    image_b64_jpeg: str,
    max_tokens: int = 2400,
    temperature: float = 0.1,
    timeout: float | None = None,
    json_schema: dict[str, Any] | None = None,
    think: bool = False,
) -> str:
    """Phase O.3 — call the self-hosted Gemma-4 E2B HF Space.

    The Space exposes a FastAPI ``/predict`` endpoint that wraps
    llama-cpp-python / llama-server.

    Optional payload knobs (the proxy ignores unknown fields, so older
    builds remain compatible):

    * ``json_schema``  — when given, the proxy is expected to forward
      it to llama-server as ``response_format={"type":"json_schema",
      "json_schema":{...}}`` to grammar-constrain the output.
    * ``think``        — when False (default for the closet AddItem
      flow), the proxy should pass
      ``--chat-template-kwargs {"enable_thinking": false}`` /
      ``--reasoning-budget 0`` to llama-server (the current
      ``dressapp-eyes`` container already launches with these defaults).
      When True, callers wanting the model to "think" before
      answering (e.g. Brain experiments) can flip it on per request.

    Failures here are surfaced as ``RuntimeError`` so the outer
    routing can swap to the Gemini fallback. That keeps AddItem
    working even when the Space is sleeping or 5xxing.
    """
    space_url = (settings.EYES_GEMMA_SPACE_URL or "").rstrip("/")
    if not space_url:
        raise RuntimeError("EYES_GEMMA_SPACE_URL not configured.")

    payload: dict[str, Any] = {
        "system": system_prompt,
        "prompt": user_text,
        "image_b64": image_b64_jpeg,
        "image_mime": "image/jpeg",
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        # Trigger llama.cpp grammar-constrained JSON when the Space
        # supports it; older builds ignore the flag harmlessly.
        "json_mode": True,
        # Switchable reasoning. The current dressapp-eyes container
        # launches llama-server with enable_thinking=false; we still
        # send the flag every call so a future proxy build can honour
        # per-request overrides without redeploys.
        "enable_thinking": bool(think),
        "think": bool(think),  # alias for forward-compat
    }
    if json_schema is not None:
        # The dressapp-eyes proxy should forward this to llama-server's
        # OpenAI-compatible response_format. Unknown to older proxies
        # → ignored harmlessly.
        payload["json_schema"] = json_schema
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "eyes_garment_response",
                "strict": True,
                "schema": json_schema,
            },
        }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    # Bearer auth between backend and the Eyes service. Prefer the
    # dedicated EYES_API_TOKEN (used on the self-hosted Hetzner deploy
    # where the HF token shouldn't be reaching the inference container
    # on every call); fall back to EYES_HF_TOKEN for the legacy HF
    # Space deploy where the same token gates both model download and
    # request auth.
    bearer = settings.EYES_API_TOKEN or settings.EYES_HF_TOKEN
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    timeout_s = float(
        timeout if timeout is not None else settings.EYES_GEMMA_TIMEOUT_S
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout_s) as cli:
            resp = await cli.post(
                f"{space_url}/predict", json=payload, headers=headers,
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gemma Space network error: {exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Gemma Space {resp.status_code}: {resp.text[:300]}"
        )
    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gemma Space non-JSON response: {exc}") from exc

    output = (body or {}).get("output")
    if not output or not isinstance(output, str):
        # Surface the empty-output condition together with the
        # adjacent metadata so logs immediately reveal whether the
        # Space ran in vision_disabled mode or just generated zero
        # tokens. Common Phase-1 case: vision_disabled=true while
        # the caller passed only an image (no text grounding).
        meta = {
            "output_type": type(output).__name__,
            "output_preview": (str(output)[:120] if output is not None else None),
            "vision_disabled": (body or {}).get("vision_disabled"),
            "vision_used": (body or {}).get("vision_used"),
            "tokens_completion": (body or {}).get("tokens_completion"),
            "finish_reason": (body or {}).get("finish_reason"),
        }
        raise RuntimeError(
            f"Gemma Space empty/invalid output ({meta})"
        )
    if body.get("vision_disabled"):
        # Phase-1 expected state — log once per call so we can spot
        # how often we're degrading. Not an error.
        logger.info(
            "Gemma Space replied with vision_disabled=true (Phase 1 text-only)."
        )
    logger.info(
        "Gemma Space OK tokens=%s+%s elapsed_ms=%s",
        body.get("tokens_prompt"),
        body.get("tokens_completion"),
        body.get("elapsed_ms"),
    )
    return output



SYSTEM_PROMPT = (
    "You are The Eyes \u2014 DressApp's visual garment analyst. You look at "
    "a photograph. If there are garments present in the photograph, analyse the photogaph (which may contain one or more garments) and "
    "describe each item in exhaustive, merchandisable detail. Your output "
    "is used to auto-fill an Add-Item form that a user will review, so be "
    "confident but never invent sensitive claims (e.g. do not guess a "
    "specific brand unless clearly visible; leave brand blank otherwise).\n\n"
    "Return ONLY a JSON value with one of two shapes:\n"
    "  \u2022 a single JSON object when one garment is visible, or\n"
    "  \u2022 a JSON array of such objects when multiple garments are visible, or\n"
    "  \u2022 a 'No Garments detected' message\n"
    " Never wrap the result in extra commentary or markdown.\n"
    "Each garment object has the following shape (all keys optional except "
    "`title`):\n"
    "{\n"
    '  "name": string,                     // 2\u20135 words. Must be UNIQUE & distinguishing \u2014 weave in a defining detail (material, fit, vibe, pattern, era, hardware, neckline, wash) so the user never ends up with 12 generic "Black T-shirt" rows. The pattern is "<distinguishing detail> + <core garment>" \u2014 e.g. heavyweight boxy + tee, ribbed slim + crewneck, vintage pocket + tee. Render that pattern in the OUTPUT LANGUAGE specified by the user message; do NOT echo English examples verbatim.\n'
    '  "title": string,                    // fallback short title (required). Same uniqueness rules as `name`. Same output language as `name`.\n'
    '  "caption": string,                  // ONE confident, vivid sentence in the OUTPUT LANGUAGE describing what makes this piece tick \u2014 silhouette, surface detail, what it pairs with. Max 240 chars. NEVER hedge: forbid "seems", "appears", "probably", "looks like", "might be". State observations directly. If `state` is "used" and `condition` is "bad", end with one short repair/enhancement tip.\n'
    '  "category": string,                 // top bucket: "Top", "Bottom", "Outerwear", "Full Body", "Footwear", "Accessories", "Underwear"\n'
    '  "sub_category": string,             // e.g. "Shirt", "Pants", "Dress", "Coat", "Sneakers"\n'
    '  "item_type": string,                // specific type: "Oxford shirt", "Mini-dress", "Crew-neck sweater"\n'
    '  "brand": string|null,               // only if legibly visible\n'
    '  "gender": "men"|"women"|"unisex"|"kids",\n'
    '  "dress_code": "casual"|"smart-casual"|"business"|"formal"|"athletic"|"loungewear",\n'
    '  "season": string[],                 // any of: "spring","summer","fall","winter","all"\n'
    '  "tradition": string|null,           // cultural/religious pattern if clearly present (e.g. "arabic","jewish","indian"), else null\n'
    '  "colors":           [{"name": string, "pct": integer 0..100}, ...],  // sum \u2248 100\n'
    '  "fabric_materials": [{"name": string, "pct": integer 0..100}, ...],  // sum \u2248 100; infer likely composition\n'
    '  "pattern": string,                  // "solid","striped","plaid","floral","herringbone","polka","paisley","geometric","abstract"\n'
    '  "state": "new"|"used",\n'
    '  "condition": "bad"|"fair"|"good"|"excellent",\n'
    '  "quality": "budget"|"mid"|"premium"|"luxury",\n'
    '  "size": string|null,                // only if a label/tag is readable, else null\n'
    '  "price_cents": integer|null,        // estimated resale value in USD cents, only if confident; else null\n'
    '  "repair_advice": string|null,       // a short, warm, actionable tip if condition==\"bad\" (e.g. \"Minor pilling on the sleeves \u2014 a fabric shaver will restore the surface.\"); null otherwise\n'
    '  "tags": string[]                    // 3\u20138 searchable keywords\n'
    "}\n\n"
    "Style rules for the free-text fields (`name`, `title`, `caption`, "
    "`tags`, `repair_advice`):\n"
    "  1. LANGUAGE \u2014 honour the OUTPUT LANGUAGE specified at the "
    "top of the user message. It applies equally to short label-like "
    "fields (`name`, `title`) and long descriptive ones (`caption`). "
    "JSON keys and the listed enum tokens always stay in English.\n"
    "  2. CONFIDENCE \u2014 state observations directly. Never hedge "
    "with \"seems\", \"appears\", \"probably\", \"looks like\", "
    "\"might be\", \"possibly\", \"kind of\". You are the expert; "
    "commit to the call. \"There's a cute cat print.\" not \"There "
    "seems to be an animal print, probably a cat.\"\n"
    "  3. UNIQUENESS \u2014 `name` and `title` must be distinguishing. "
    "Imagine the user already owns ten black tees; pick a detail no "
    "other shirt in a closet would share (texture, weight, neckline, "
    "wash, hardware, vibe, era).\n"
    "  4. VOICE \u2014 thoughtful editor, never salesy, never robotic. "
    "No emojis, no markdown, no hashtags, no #tags inside text "
    "fields."
)


# ─────────────────────────────────────────────────────────────────────
# Phase O.6 — single-pass-only suffix
# ─────────────────────────────────────────────────────────────────────
# Appended to ``SYSTEM_PROMPT`` ONLY when the caller is the single-pass
# pipeline (``EYES_ONE_PASS=true`` or the ``analyze_outfit_one_pass``
# helper). Teaches Eyes to additionally emit a ``region`` object with
# a tightly-fitted bbox on the 0..1000 normalised grid for every
# garment. Crucially we keep this OUT of the legacy ``SYSTEM_PROMPT``
# so:
#   1. legacy multi-call path keeps validating against the existing
#      schema (region is optional in the schema, never required there);
#   2. legacy LoRA evaluation runs are unaffected (no prompt drift);
#   3. the one-pass change can be A/B'd without a deploy.
#
# One-shot example included so Gemma-4 E2B can pattern-match the grid
# convention without needing a fine-tune (Option α per the proposal).
SYSTEM_PROMPT_ONE_PASS_SUFFIX = (
    "\n\n"
    "ADDITIONAL OUTPUT REQUIREMENT \u2014 spatial region.\n"
    "For EACH garment object you return, include a `region` block:\n"
    "  region: {\n"
    "    bbox: [ymin, xmin, ymax, xmax],   // integers on a 0..1000 grid\n"
    "    confidence: number 0..1 (optional),\n"
    "    is_full_frame: boolean (optional)\n"
    "  }\n"
    "Rules for `bbox`:\n"
    "  \u2022 Coordinates are normalised: 0 is the top/left edge, 1000 is "
    "the bottom/right edge. Use integers; ignore the source pixel size.\n"
    "  \u2022 Tightly enclose the visible garment, INCLUDING sleeves, "
    "collars, hems. EXCLUDE the wearer's face and bare skin.\n"
    "  \u2022 If the photo is a clean, single-garment shot (flat lay, "
    "studio still, ghost mannequin) and there is no other garment in "
    "frame, set `region.bbox = [0, 0, 1000, 1000]` and "
    "`region.is_full_frame = true`. This is the common case.\n"
    "  \u2022 If multiple garments overlap, each garment's bbox encloses "
    "ONLY that garment (the bboxes may overlap each other).\n"
    "  \u2022 If a garment is mostly occluded (less than ~20% visible), "
    "omit it from the output entirely \u2014 do not return a near-empty "
    "bbox.\n"
    "\n"
    "Worked example. Input: a full-length photo of a person wearing a "
    "white t-shirt tucked into blue jeans, plus white sneakers. "
    "Correct output (truncated for clarity):\n"
    "  [\n"
    "    { \"title\": \"White crew tee\", "
    "\"category\": \"Top\", "
    "\"region\": {\"bbox\": [180, 280, 520, 720], \"confidence\": 0.92, "
    "\"is_full_frame\": false} },\n"
    "    { \"title\": \"Blue straight jeans\", "
    "\"category\": \"Bottom\", "
    "\"region\": {\"bbox\": [520, 290, 880, 720], \"confidence\": 0.94, "
    "\"is_full_frame\": false} },\n"
    "    { \"title\": \"White low-top sneakers\", "
    "\"category\": \"Footwear\", "
    "\"region\": {\"bbox\": [880, 320, 985, 700], \"confidence\": 0.88, "
    "\"is_full_frame\": false} }\n"
    "  ]"
)


def _build_system_prompt(*, one_pass: bool) -> str:
    """Return the full system prompt for an Eyes call.

    ``one_pass=False`` returns the legacy prompt verbatim so existing
    callers (per-crop analysis, reconstruction re-validate, the old
    ``analyze_outfit``) keep working bit-for-bit. ``one_pass=True``
    appends the bbox-emission rules + one-shot example.
    """
    if one_pass:
        return SYSTEM_PROMPT + SYSTEM_PROMPT_ONE_PASS_SUFFIX
    return SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────────────
# Canonical JSON schema for Eyes responses. Sent to llama-server via
# ``response_format={"type":"json_schema","json_schema":{...}}`` so the
# decoder is grammar-constrained to a valid garment object (or array
# of garment objects). Kept in lockstep with ``SYSTEM_PROMPT``.
#
# The wrapper uses ``oneOf`` so the model can return either a single
# garment object or a JSON array of garment objects, matching the
# user-message instruction. Empty array `[]` is allowed (no garment).
# ─────────────────────────────────────────────────────────────────────
_GARMENT_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["title"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "title": {"type": "string"},
        "caption": {"type": "string", "maxLength": 240},
        "category": {
            "type": "string",
            "enum": [
                "Top", "Bottom", "Outerwear", "Full Body",
                "Footwear", "Accessories", "Underwear",
            ],
        },
        "sub_category": {"type": "string"},
        "item_type": {"type": "string"},
        "brand": {"type": ["string", "null"]},
        "gender": {
            "type": "string",
            "enum": ["men", "women", "unisex", "kids"],
        },
        "dress_code": {
            "type": "string",
            "enum": [
                "casual", "smart-casual", "business",
                "formal", "athletic", "loungewear",
            ],
        },
        "season": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["spring", "summer", "fall", "winter", "all"],
            },
        },
        "tradition": {"type": ["string", "null"]},
        "colors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "pct"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "pct": {"type": "integer", "minimum": 0, "maximum": 100},
                },
            },
        },
        "fabric_materials": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "pct"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "pct": {"type": "integer", "minimum": 0, "maximum": 100},
                },
            },
        },
        "pattern": {
            "type": "string",
            "enum": [
                "solid", "striped", "plaid", "floral", "herringbone",
                "polka", "paisley", "geometric", "abstract",
            ],
        },
        "state": {"type": "string", "enum": ["new", "used"]},
        "condition": {
            "type": "string",
            "enum": ["bad", "fair", "good", "excellent"],
        },
        "quality": {
            "type": "string",
            "enum": ["budget", "mid", "premium", "luxury"],
        },
        "size": {"type": ["string", "null"]},
        "price_cents": {"type": ["integer", "null"], "minimum": 0},
        "repair_advice": {"type": ["string", "null"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 16,
        },
        # ── Phase O.6 — single-pass region info ───────────────────────
        # Optional spatial metadata. Only populated when the caller is
        # the single-pass pipeline (``EYES_ONE_PASS=true``). Legacy
        # multi-call pipelines never request this field, so the schema
        # leaves it out of ``required`` and the existing crops/Gemini
        # paths continue to validate without changes.
        #
        # The bbox is on a normalised 0..1000 grid so the model can
        # answer in pure integers regardless of the source image's
        # resolution; the backend rescales to pixels using the
        # ``size`` it sent in the user message.
        "region": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["bbox"],
            "properties": {
                "bbox": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 1000},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": (
                        "[ymin, xmin, ymax, xmax] on the 0..1000 normalised "
                        "grid. Origin top-left; ymax > ymin; xmax > xmin."
                    ),
                },
                "confidence": {
                    "type": ["number", "null"],
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Self-reported confidence in the bbox (optional).",
                },
                "is_full_frame": {
                    "type": ["boolean", "null"],
                    "description": (
                        "True when the photo is already a clean, single-garment "
                        "shot and the bbox is [0, 0, 1000, 1000]."
                    ),
                },
            },
        },
    },
}

# Top-level wrapper: single garment object OR list of garment objects.
EYES_JSON_SCHEMA: dict[str, Any] = {
    "oneOf": [
        _GARMENT_OBJECT_SCHEMA,
        {
            "type": "array",
            "items": _GARMENT_OBJECT_SCHEMA,
        },
    ],
}



# Human-readable names for each supported UI language (matches
# frontend/src/lib/i18n.js). Enum-ish values and JSON keys MUST stay in
# English so downstream Pydantic validation never 422s.
_LANG_NAMES = {
    "en": "English",
    "he": "Hebrew",
    "ar": "Arabic",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "hi": "Hindi",
}


def _language_directive(code: str | None) -> str:
    """No-op now — the language directive lives at the top of the
    user message (see :func:`_user_prompt`), matching the proven
    pattern used by ``stylist_brain``. Kept as a callable so the rest
    of ``analyze()`` doesn't need to branch on language.
    """
    return ""


def _user_prompt(code: str | None) -> str:
    """Build the user-message prompt for ``analyze()``.

    For non-English locales we prepend the **proven** ``OUTPUT
    LANGUAGE = Name (xx)`` preamble (same format used by
    ``stylist_brain.py`` and ``gemini_stylist.py``) at the TOP of the
    user message, where the model sees it last before generating.
    Listing the free-text fields explicitly forces the model to apply
    the language rule to short label-like values (``name`` / ``title``)
    that it otherwise leaves in English.

    JSON keys and the schema's closed-vocabulary enums (``category``,
    ``gender``, ``dress_code``, ``season``, ``pattern``, ``state``,
    ``condition``, ``quality``) deliberately stay in English so the
    downstream sanitiser / DB / UI lookups don't have to know every
    locale's translation.
    """
    base = (
        "Analyse this photograph. If one garment is visible return a single "
        "JSON object; if multiple garments are visible return a JSON array "
        "of such objects. No commentary."
    )
    code = (code or "en").lower()
    if code == "en":
        return base
    lang_name = _LANG_NAMES.get(code, code)
    return (
        f"**OUTPUT LANGUAGE = {lang_name} ({code}).** Every free-text "
        f"field (`name`, `title`, `caption`, `tags`, `repair_advice`, "
        f"`sub_category`, `item_type`, `colors[*].name`, "
        f"`fabric_materials[*].name`) MUST be written in fluent, "
        f"idiomatic {lang_name}. JSON keys and enum tokens "
        f"(`category`, `gender`, `dress_code`, `season`, `pattern`, "
        f"`state`, `condition`, `quality`) stay in English.\n\n"
        + base
    )


def _extract_json(raw: str) -> dict[str, Any] | list[dict[str, Any]]:
    """Pull the JSON payload out of a model response.

    Returns either:
      * dict  — the typical single-garment response, OR
      * list[dict] — Eyes v3 (Gemma 4) can return a JSON array when the
        photo contains multiple garments. Callers that expect a single
        item should handle the list case (see ``analyze()``).
    """
    if not raw:
        return {}

    # 1) ```json fenced``` — prefer array form, then object.
    for pattern in (r"```(?:json)?\s*(\[.*?\])\s*```", r"```(?:json)?\s*(\{.*?\})\s*```"):
        m = re.search(pattern, raw, flags=re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:  # noqa: BLE001
                pass

    # 2) Bare array: take the outermost [...] span.
    a_first = raw.find("[")
    a_last = raw.rfind("]")
    o_first = raw.find("{")
    o_last = raw.rfind("}")

    # Prefer array if it brackets an object (i.e. real list-of-garments,
    # not just a stray "[" inside a string field). Heuristic: the array
    # span must enclose at least one "{".
    if (
        a_first != -1 and a_last != -1 and a_last > a_first
        and (o_first == -1 or a_first < o_first <= a_last)
    ):
        try:
            return json.loads(raw[a_first : a_last + 1])
        except Exception:  # noqa: BLE001
            pass

    # 3) Bare object.
    if o_first != -1 and o_last != -1 and o_last > o_first:
        try:
            return json.loads(raw[o_first : o_last + 1])
        except Exception:  # noqa: BLE001
            pass

    # 4) Last resort — model returned valid JSON with no surrounding text.
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def _coerce_single_garment(
    parsed: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Collapse a list-of-garments response into the single-item contract.

    Eyes v3 (Gemma 4) sometimes returns ``[{...}, {...}]`` when a crop
    accidentally bundles two garments, or in the already-cropped fast
    path. ``analyze()`` is contractually single-garment, so we pick the
    first entry (model orders by prominence) and log so we can monitor
    how often this happens.
    """
    if isinstance(parsed, list):
        items = [x for x in parsed if isinstance(x, dict)]
        if not items:
            return {}
        if len(items) > 1:
            logger.info(
                "Eyes returned %d garments in one call; using the first "
                "(consider tightening crop or upgrading to multi-item path)",
                len(items),
            )
        return items[0]
    return parsed if isinstance(parsed, dict) else {}


def _shrink_for_vision(image_bytes: bytes, *, max_side: int = 1280, q: int = 82) -> bytes:
    """Keep the API payload light; Gemini vision is happy with ~1280px long side."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return image_bytes


DETECT_SYSTEM_PROMPT = (
    "You are DressApp's object detector. Look at a photo and enumerate EVERY "
    "visible fashion item \u2014 garments, outerwear, footwear, bags, "
    "accessories (belts, scarves, hats, glasses), and jewelry (rings, "
    "necklaces, earrings, watches). Do not guess things that are not "
    "clearly visible. Ignore the person, skin, hair, and background.\n\n"
    "CRITICAL RULES:\n"
    "- Return **exactly one** bounding box per distinct physical item. "
    "Never output multiple boxes for the same piece (e.g. do not return "
    "both a \"shirt\" box and a \"sleeve\" box for the same shirt).\n"
    "- If you are uncertain whether two regions are the same garment, "
    "merge them into a single box that covers both.\n"
    "- A pair (shoes, earrings, gloves) counts as ONE item \u2014 use a "
    "single box that contains both pieces.\n"
    "- Do NOT include a full-frame box covering the whole outfit \u2014 "
    "only individual items.\n\n"
    "For each item, return a tight bounding box in normalized coordinates "
    "on a 0\u20131000 scale (where 0 is top/left and 1000 is bottom/right), "
    "using Gemini's standard ``[ymin, xmin, ymax, xmax]`` order.\n\n"
    "Return ONLY a JSON object of the form:\n"
    '{\n'
    '  "items": [\n'
    '    {\n'
    '      "label": "short lowercase tag like \'oxford shirt\' or \'gold watch\'",\n'
    '      "kind": "garment"|"outerwear"|"footwear"|"bag"|"accessory"|"jewelry",\n'
    '      "bbox": [ymin, xmin, ymax, xmax]   // integers, 0\u20131000\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "If only a single item fills the frame, return exactly one entry. "
    "Never return an empty list \u2014 if you cannot confidently detect "
    "anything, return a single entry covering the whole frame with "
    'label="garment" and kind="garment".'
)


_BBOX_PADDING_PCT = 0.04  # relative padding around each detected bbox
_MIN_CROP_AREA_PCT = 0.008  # ignore detections smaller than ~1% of the frame
_NMS_IOU_THRESHOLD = 0.35  # two boxes with IoU above this are considered duplicates
# A single bbox covering at least this fraction of the frame means the
# user uploaded an already-tight garment shot; cropping further would
# chop the item in half. We skip the crop step in that case.
# 0.45 captures the common "single garment on clean background with
# surrounding whitespace" product-shot pattern.
_SINGLE_ITEM_AREA_FRAC = 0.45
# When multiple detections all have the same "kind" AND their combined
# union bbox covers less than this fraction of the frame, they are
# almost certainly sub-parts of one already-cropped garment (collar,
# sleeve, hem, etc.). We collapse them into one whole-frame item.
_SUBPART_UNION_FRAC = 0.55


def _iou_norm(a: list[int], b: list[int]) -> float:
    """Intersection-over-union of two ``[ymin, xmin, ymax, xmax]`` boxes."""
    ay1, ax1, ay2, ax2 = a
    by1, bx1, by2, bx2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0, (ax2 - ax1)) * max(0, (ay2 - ay1))
    area_b = max(0, (bx2 - bx1)) * max(0, (by2 - by1))
    union = area_a + area_b - inter
    return float(inter) / float(union) if union > 0 else 0.0


def _containment(a: list[int], b: list[int]) -> float:
    """Fraction of the smaller box contained inside the other.

    Catches the case where the detector returns a fine-grained part box
    (e.g. a sleeve) nested inside a full-item box (e.g. the shirt).
    """
    ay1, ax1, ay2, ax2 = a
    by1, bx1, by2, bx2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    smaller = min(area_a, area_b)
    return inter / float(smaller)


# Kind affinities so NMS still collapses near-duplicates even when the
# detector hands back slightly different labels (e.g. "shirt" + "top").
_SIMILAR_KINDS = {
    "garment": {"garment", "outerwear"},
    "outerwear": {"outerwear", "garment"},
    "footwear": {"footwear"},
    "bag": {"bag"},
    "accessory": {"accessory", "jewelry"},
    "jewelry": {"jewelry", "accessory"},
}


def _same_thing(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Heuristic \u2014 are two detections the same physical item?"""
    bbox_a, bbox_b = a.get("bbox"), b.get("bbox")
    if not (isinstance(bbox_a, list) and isinstance(bbox_b, list)):
        return False
    iou = _iou_norm(bbox_a, bbox_b)
    contain = _containment(bbox_a, bbox_b)
    kind_a = (a.get("kind") or "garment").lower()
    kind_b = (b.get("kind") or "garment").lower()
    compatible_kind = kind_b in _SIMILAR_KINDS.get(kind_a, {kind_a})
    # Strong overlap -> duplicate, regardless of kind.
    if iou >= _NMS_IOU_THRESHOLD:
        return True
    # One clearly nested inside the other AND compatible kind -> duplicate.
    if contain >= 0.8 and compatible_kind:
        return True
    return False


def _nms_detections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-max-suppression over detector output.

    Keeps the larger bbox when two detections describe the same item,
    so one physical garment can only ever yield a single card.
    """
    def _area(it: dict[str, Any]) -> int:
        y1, x1, y2, x2 = it["bbox"]
        return max(0, (x2 - x1)) * max(0, (y2 - y1))

    # Sort by area DESC so the dominant (larger) box wins.
    sorted_items = sorted(items, key=_area, reverse=True)
    kept: list[dict[str, Any]] = []
    for it in sorted_items:
        if any(_same_thing(it, k) for k in kept):
            continue
        kept.append(it)
    return kept


def _is_unidentifiable(analysis: dict[str, Any] | None) -> bool:
    """Return True when the LLM analysis indicates it couldn't make sense
    of the crop \u2014 used to drop noise crops from the closet rather
    than save useless "Unidentifiable Garment" cards.

    Triggers on three signals (any of them is enough):

    1. Title contains a give-up phrase ("unidentifiable", "obscured",
       "unknown", "cannot identify", "not visible").
    2. Caption contains a give-up phrase or starts with the LLM's
       boilerplate refusal pattern ("the item in this photo is not...").
    3. Both ``item_type`` *and* ``sub_category`` are empty/missing \u2014
       a sign the LLM gave up on classifying the garment.
    """
    if not analysis:
        return True
    GIVE_UP_PHRASES = (
        "unidentifiable",
        "obscured",
        "cannot identify",
        "can't identify",
        "not clearly visible",
        "not identifiable",
        "unable to identify",
        "no garment",
        "no clothing",
        "unknown garment",
        "unknown item",
    )
    title = (analysis.get("title") or "").lower()
    caption = (analysis.get("caption") or "").lower()
    if any(p in title for p in GIVE_UP_PHRASES):
        return True
    if any(p in caption for p in GIVE_UP_PHRASES):
        return True
    item_type = (analysis.get("item_type") or "").strip()
    sub_category = (analysis.get("sub_category") or "").strip()
    if not item_type and not sub_category:
        return True
    return False


def _looks_already_cropped(detections: list[dict[str, Any]]) -> bool:
    """Return True when the photo is already a tight single-item shot.

    Three signals trigger this:

    1. **Single large detection** \u2014 exactly one bbox remains after NMS
       and it covers at least ``_SINGLE_ITEM_AREA_FRAC`` of the frame.
    2. **Cluster of sub-parts** \u2014 multiple detections share the same
       ``kind`` AND their union bbox covers less than
       ``_SUBPART_UNION_FRAC`` of the frame, which is the tell-tale
       pattern of the model hallucinating a collar/sleeve/hem as
       separate items on an already-cropped garment photo.
    3. **Heavily-overlapping detections** \u2014 multiple detections
       overlap so much that ``sum(individual_areas) > 1.4 * union_area``.
       This catches the SegFormer corner case where a single garment
       with a complex / novelty pattern gets labeled as both
       ``Upper-clothes`` and ``Dress`` (or shirt + jacket, etc.) on
       the same pixels. Without this we treat the photo as multi-item
       and shred it into nonsensical fragments.

    In all cases we skip the server-side cropping step and analyse
    the image as a single item so we never shred an already-clean
    product shot.
    """
    if not detections:
        return True  # nothing detectable \u2014 safer to analyse whole frame
    frame_area = 1000 * 1000

    def _area(bbox: list[int]) -> int:
        y1, x1, y2, x2 = bbox
        return max(0, (x2 - x1)) * max(0, (y2 - y1))

    areas = [_area(d["bbox"]) for d in detections]
    largest_area = max(areas) if areas else 0

    # Signal 0 (NEW, takes precedence): any single detection that already
    # covers >= the single-item threshold means the photo is dominated by
    # one garment. Other small detections are SegFormer label-confusion
    # fragments (e.g. labelling part of a patterned t-shirt as "Dress" and
    # another part as "Upper-clothes"). Treat as single-item so we feed
    # the WHOLE photo through rembg + Gemini once instead of shredding it
    # into nonsensical sub-crops.
    if largest_area >= frame_area * _SINGLE_ITEM_AREA_FRAC:
        return True

    # Signal 1: one dominant detection (only triggers when nothing crossed
    # the threshold above — kept for the ``len == 1`` corner cases).
    if len(detections) == 1:
        if largest_area >= frame_area * _SINGLE_ITEM_AREA_FRAC:
            return True
        # A single tiny detection on a clean-looking frame also hints at
        # an over-zealous sub-part crop.
        if largest_area <= frame_area * 0.25:
            return True
        return False

    # Signal 3: heavily-overlapping detections imply one garment with
    # conflicting class labels.
    sum_areas = sum(areas)
    ymins = [d["bbox"][0] for d in detections]
    xmins = [d["bbox"][1] for d in detections]
    ymaxs = [d["bbox"][2] for d in detections]
    xmaxs = [d["bbox"][3] for d in detections]
    union = max(1, (max(ymaxs) - min(ymins)) * (max(xmaxs) - min(xmins)))
    overlap_ratio = sum_areas / float(union)
    if overlap_ratio >= 1.4:
        return True

    # Signal 2: several detections of the same kind, all clustered inside
    # a small area (collar / sleeve / hem hallucinations).
    kinds = {(d.get("kind") or "garment").lower() for d in detections}
    if len(kinds) > 1:
        return False
    return union <= frame_area * _SUBPART_UNION_FRAC


# -------------------- enum sanitisers --------------------
# The Flash tier of Gemini occasionally confuses ``state`` (new/used) with
# ``condition`` (bad/fair/good/excellent) or returns values in slightly
# different casing (e.g. "Smart Casual" vs "smart-casual"). Rather than
# reject those responses with a 422 at save time, we coerce them to the
# nearest valid enum value so the auto-fill stays useful and the user
# can still edit freely.
_VALID_STATE = {"new", "used"}
_VALID_CONDITION = {"bad", "fair", "good", "excellent"}
_VALID_QUALITY = {"budget", "mid", "premium", "luxury"}
_VALID_GENDER = {"men", "women", "unisex", "kids"}
_VALID_DRESS_CODE = {
    "casual", "smart-casual", "business", "formal", "athletic", "loungewear",
}
_VALID_PATTERN = {
    "solid", "striped", "plaid", "floral", "herringbone",
    "polka", "paisley", "geometric", "abstract",
}


def _norm_str(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    return v.strip().lower().replace("_", "-")


def _coerce_enum_field(
    parsed: dict[str, Any],
    key: str,
    valid: set[str],
    *,
    aliases: dict[str, str] | None = None,
    default: str | None = None,
) -> None:
    """Normalise ``parsed[key]`` to a value in ``valid`` (or ``None``).

    Steps: strip → lower via ``_norm_str`` → remap via ``aliases`` →
    accept only if in ``valid``. When the coerced value is invalid the
    field is set to ``default`` (typically ``None``) so Pydantic's
    optional-enum validators stay happy.
    """
    value = _norm_str(parsed.get(key))
    if value and aliases:
        value = aliases.get(value, value)
    parsed[key] = value if value in valid else default


def _coerce_seasons(parsed: dict[str, Any]) -> None:
    """Coerce ``parsed['season']`` to a validated list (may be empty)."""
    allowed = {"spring", "summer", "fall", "autumn", "winter", "all"}
    raw = parsed.get("season") or []
    if isinstance(raw, str):
        raw = [raw]
    seasons: list[str] = []
    for entry in raw:
        tok = _norm_str(entry)
        if tok == "autumn":
            tok = "fall"
        if tok in allowed:
            seasons.append(tok)
    parsed["season"] = seasons


# Alias tables for the model's common off-spec echoes. Keeping these at
# module scope lets us unit-test them directly without instantiating the
# vision service.
_GENDER_ALIASES = {
    "male": "men", "female": "women", "uni": "unisex", "kid": "kids",
}
_CONDITION_ALIASES = {"poor": "bad", "very-good": "excellent"}
_QUALITY_ALIASES = {
    "cheap": "budget", "entry": "budget", "basic": "budget",
    "mid-range": "mid", "standard": "mid",
    "high": "premium", "high-end": "premium",
}


def _normalise_dress_code(raw: str | None) -> str | None:
    """Return the dress-code token after space→hyphen + common renames."""
    value = _norm_str(raw)
    if not value:
        return None
    value = value.replace(" ", "-")
    if value == "athleisure":
        value = "athletic"
    if value == "lounge":
        value = "loungewear"
    return value


def _coerce_enums(parsed: dict[str, Any]) -> dict[str, Any]:
    """Best-effort coercion of AI-returned enum values.

    * Unknown / empty values are dropped rather than kept, so Pydantic's
      optional-enum fields stay valid (None instead of an unknown literal).
    * ``state`` is the main hazard: the model sometimes echoes the
      ``condition`` value there. We default to ``used``; the user can
      flip to ``new`` in the form.
    """
    _coerce_enum_field(
        parsed, "gender", _VALID_GENDER, aliases=_GENDER_ALIASES,
    )
    parsed["dress_code"] = (
        _normalise_dress_code(parsed.get("dress_code"))
        if _normalise_dress_code(parsed.get("dress_code")) in _VALID_DRESS_CODE
        else None
    )
    _coerce_enum_field(
        parsed, "condition", _VALID_CONDITION, aliases=_CONDITION_ALIASES,
    )
    # ``state`` has a sensible default unlike the other enums — the form
    # can round-trip "used" without surprising the user.
    s = _norm_str(parsed.get("state"))
    parsed["state"] = s if s in _VALID_STATE else "used"
    _coerce_enum_field(
        parsed, "quality", _VALID_QUALITY, aliases=_QUALITY_ALIASES,
    )
    _coerce_enum_field(parsed, "pattern", _VALID_PATTERN)
    _coerce_seasons(parsed)
    return parsed


def _crop_to_bbox(
    image_bytes: bytes, bbox_norm: list[int]
) -> tuple[bytes, tuple[int, int, int, int]] | None:
    """Return (cropped_jpeg_bytes, (x1,y1,x2,y2)) for a 0\u20131000 bbox.

    ``bbox_norm`` is ``[ymin, xmin, ymax, xmax]`` on a 0\u20131000 scale.
    Adds a small padding and clamps to the image bounds.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    w, h = img.size
    try:
        ymin, xmin, ymax, xmax = [int(v) for v in bbox_norm]
    except Exception:  # noqa: BLE001
        return None
    # Validate scale \u2014 expect 0..1000
    if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
        return None
    x1 = max(0, int(xmin / 1000.0 * w - w * _BBOX_PADDING_PCT))
    y1 = max(0, int(ymin / 1000.0 * h - h * _BBOX_PADDING_PCT))
    x2 = min(w, int(xmax / 1000.0 * w + w * _BBOX_PADDING_PCT))
    y2 = min(h, int(ymax / 1000.0 * h + h * _BBOX_PADDING_PCT))
    if x2 - x1 <= 4 or y2 - y1 <= 4:
        return None
    area_pct = ((x2 - x1) * (y2 - y1)) / float(max(1, w * h))
    if area_pct < _MIN_CROP_AREA_PCT:
        return None
    crop = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue(), (x1, y1, x2, y2)


class GarmentVisionService:
    def __init__(self) -> None:
        # We tolerate a missing EMERGENT_LLM_KEY if HF is configured for
        # both analysis AND detection. In practice we keep Gemini Flash
        # for detection, so both keys are typically required.
        self.model = settings.GARMENT_VISION_MODEL
        self.provider = settings.GARMENT_VISION_PROVIDER
        # Detection stays on Gemini Flash for Phase A.
        self.detect_provider = settings.GARMENT_VISION_DETECT_PROVIDER
        self.detect_model = settings.GARMENT_VISION_DETECT_MODEL
        # Per-crop analyser (multi-item pipeline).
        self.crop_model = settings.GARMENT_VISION_CROP_MODEL
        self.max_items = settings.GARMENT_VISION_MAX_ITEMS
        # Gemini chat key — direct GEMINI_API_KEY (production) wins,
        # else EMERGENT_LLM_KEY (dev). litellm handles routing.
        self.api_key = settings.gemini_chat_key
        # Fail fast when the service cannot actually run anything.
        if self.provider == "gemini" and not self.api_key:
            raise RuntimeError(
                "GARMENT_VISION_PROVIDER=gemini but neither GEMINI_API_KEY "
                "nor EMERGENT_LLM_KEY is set."
            )
        if self.provider == "hf" and not settings.HF_TOKEN:
            raise RuntimeError(
                "GARMENT_VISION_PROVIDER=hf but HF_TOKEN is unset."
            )
        if self.detect_provider == "gemini" and not self.api_key:
            logger.warning(
                "Detection requires a Gemini chat key; multi-item pipeline will "
                "degrade to single-item analysis."
            )

    # -------------------- public API --------------------
    async def _detect_via_clothing_parser(
        self, image_bytes: bytes,
    ) -> list[dict[str, Any]] | None:
        """Try the local SegFormer-based parser. Returns the normalised
        detection list on success, or ``None`` to let the caller fall
        back to Gemini. A parser exception is logged and treated as a
        soft miss — we don't want a SegFormer hiccup to mask bad photos.
        """
        if not settings.USE_CLOTHING_PARSER:
            return None
        try:
            from app.services import clothing_parser

            parser_items = await clothing_parser.parse_garments(image_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "detect_items: clothing_parser path failed (%s), falling back",
                exc,
            )
            return None
        if not parser_items:
            return None
        logger.info(
            "detect_items: clothing_parser succeeded with %d items",
            len(parser_items),
        )
        return [
            {
                "label": p["label"].lower().replace("-", "_"),
                "kind": p["category"],
                "bbox": p["bbox"],
                "score": p["score"],
                # Preserve full-res mask so analyze_outfit can build
                # semantic PNG cutouts instead of bbox rectangles. Not
                # serialised to JSON anywhere.
                "mask": p.get("mask"),
                "source": "clothing_parser",
            }
            for p in parser_items
        ]

    async def _detect_via_gemini(
        self, image_bytes: bytes,
    ) -> list[dict[str, Any]]:
        """Gemini bbox-detection fallback. Returns a pre-NMS list of
        ``{label, kind, bbox}`` dicts (the caller applies NMS +
        validation)."""
        if self.detect_provider != "gemini":
            logger.warning(
                "Unsupported detect provider %s; returning empty detections.",
                self.detect_provider,
            )
            return []
        if not self.api_key:
            logger.warning("No Gemini chat key; skipping detection.")
            return []

        shrunk = _shrink_for_vision(image_bytes, max_side=1024, q=80)
        b64 = base64.b64encode(shrunk).decode("ascii")
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"theeyes-detect-{uuid.uuid4().hex[:12]}",
            system_message=DETECT_SYSTEM_PROMPT,
        )
        chat.with_model(self.detect_provider, self.detect_model)
        msg = UserMessage(
            text=(
                "List every fashion item visible in this photograph. "
                "Return the JSON object only."
            ),
            file_contents=[ImageContent(b64)],
        )
        t0 = time.perf_counter()
        ok = False
        last_err: str | None = None
        try:
            raw = await chat.send_message(msg)
            ok = True
        except Exception as exc:  # noqa: BLE001
            last_err = repr(exc)
            raise
        finally:
            provider_activity.record(
                "garment-vision-detect",
                ok=ok,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=last_err,
                extra={"model": self.detect_model},
            )
        parsed = _extract_json(raw or "")
        if isinstance(parsed, list):
            # Bbox detector schema is {"items": [...]} — a top-level list
            # means the model misformatted; treat as no detections.
            parsed = {}
        items = parsed.get("items") or []
        if not isinstance(items, list):
            items = []

        clean: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            bbox = it.get("bbox")
            label = (it.get("label") or "garment").strip().lower()
            kind = (it.get("kind") or "garment").strip().lower()
            if (
                not isinstance(bbox, list)
                or len(bbox) != 4
                or not all(isinstance(v, (int, float)) for v in bbox)
            ):
                continue
            clean.append(
                {"label": label, "kind": kind, "bbox": [int(v) for v in bbox]}
            )
        return clean

    async def detect_items(self, image_bytes: bytes) -> list[dict[str, Any]]:
        """Return a list of ``{label, kind, bbox}`` entries.

        Phase V: try the commercial-safe clothing parser first
        (sayeed99/segformer_b3_clothes, MIT). If it returns at least one
        garment we use those — they're pixel-accurate per-class and split
        outfits reliably. Otherwise fall back to the Gemini bbox detector
        and apply non-maximum suppression to collapse overlapping boxes.
        """
        parser_hits = await self._detect_via_clothing_parser(image_bytes)
        if parser_hits:
            return parser_hits

        clean = await self._detect_via_gemini(image_bytes)
        # Non-maximum suppression: collapse overlapping detections that
        # describe the same physical item (IoU >= 0.35 OR one box nested
        # inside the other with compatible kind).
        before = len(clean)
        clean = _nms_detections(clean)
        logger.info(
            "detect_items OK model=%s count=%d (nms removed %d) labels=%s",
            self.detect_model,
            len(clean),
            before - len(clean),
            [c["label"] for c in clean][:8],
        )
        return clean

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        model: str | None = None,
        provider: str | None = None,
        language: str | None = None,
        think: bool = False,
        one_pass: bool = False,
    ) -> dict[str, Any]:
        """Run the 17-field analyser on a single image.

        Phase O.4 routing — the **DB-backed Eyes toggle**
        (``eyes_override.get_active_provider()``) is the authoritative
        source for which model serves the request:

        * ``gemma`` -> POST to the self-hosted Gemma-4 E2B HF Space
          (``EYES_GEMMA_SPACE_URL``). Any failure (5xx, timeout,
          network error) automatically falls back to Gemini so the
          UX stays alive while the Space is sleeping/crashed; we
          tag the response with ``provider_fallback`` so the
          frontend can surface "served from Gemini fallback".
        * ``gemini`` -> direct Gemini 2.5 Flash via Emergent / Google
          chat key.

        Explicit ``provider=`` argument still wins (used by the new
        diagnostics endpoint and tests). The ``GARMENT_VISION_PROVIDER``
        env var is now only a *seed* used by ``eyes_override`` when no
        DB override has been written yet.

        ``think`` — pass through to ``_call_gemma_space``. Defaults to
        False so the closet AddItem flow stays fast & non-reasoning.
        Brain experiments / stylist callers can flip it on.

        ``one_pass`` — Phase O.6 single-pass mode. When True we append
        ``SYSTEM_PROMPT_ONE_PASS_SUFFIX`` so Eyes additionally returns
        a ``region.bbox`` per garment. The schema includes ``region``
        as optional either way; this flag is what makes the model
        actually populate it. Defaults to False so every legacy caller
        (per-crop analysis, reconstruction re-validate, direct callers
        in the closet endpoint) keeps the original prompt bit-for-bit.
        """
        from app.services import eyes_override

        shrunk = _shrink_for_vision(image_bytes)
        b64 = base64.b64encode(shrunk).decode("ascii")
        system_prompt = (
            _build_system_prompt(one_pass=one_pass)
            + _language_directive(language)
        )
        user_text = _user_prompt(language)

        # 1) Resolve the routing target.
        if provider:
            resolved = provider.strip().lower()
            routing_source = "explicit"
        else:
            resolved = (await eyes_override.get_active_provider()).lower()
            routing_source = "toggle"

        raw: str | None = None
        used_provider: str = resolved
        used_model: str = model or self.model
        used_fallback: bool = False
        fallback_reason: str | None = None

        # 2) Gemma path (toggle says gemma AND a Space URL is configured).
        if resolved == "gemma" and settings.EYES_GEMMA_SPACE_URL:
            t0 = time.perf_counter()
            try:
                raw = await _call_gemma_space(
                    system_prompt=system_prompt,
                    user_text=user_text,
                    image_b64_jpeg=b64,
                    # The Gemma-4 fine-tune is a thinking model: it spends
                    # ~600-1200 tokens reasoning inside ``<|think|> ...
                    # </think>`` before producing the JSON. Combined with
                    # the 18-field schema (~600 tokens of valid output),
                    # the default 900-token budget is too tight and the
                    # response gets cut off mid-think with empty
                    # ``content``. 2400 leaves comfortable headroom.
                    max_tokens=2400,
                    timeout=settings.EYES_GEMMA_TIMEOUT_S,
                    json_schema=EYES_JSON_SCHEMA,
                    think=think,
                )
                provider_activity.record(
                    "garment-vision",
                    ok=True,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    extra={
                        "provider": "gemma",
                        "model": "gemma-4-e2b-q4_k_m",
                        "routing_source": routing_source,
                    },
                )
                used_provider = "gemma"
                used_model = "gemma-4-e2b-q4_k_m"
            except Exception as exc:  # noqa: BLE001
                provider_activity.record(
                    "garment-vision",
                    ok=False,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    error=repr(exc),
                    extra={
                        "provider": "gemma",
                        "fallback": "gemini",
                        "routing_source": routing_source,
                    },
                )
                logger.warning(
                    "Gemma Space unavailable (%s) \u2014 falling back to Gemini.",
                    repr(exc)[:200],
                )
                used_fallback = True
                fallback_reason = repr(exc)[:200]
                resolved = "gemini"
                raw = None  # cascade into the Gemini branch below

        # 3) Gemini path (toggle says gemini, OR Gemma path failed and
        #    cascaded down here, OR gemma was selected but no Space URL
        #    is configured on this pod).
        if raw is None:
            if not self.api_key:
                raise RuntimeError(
                    "Gemini Eyes path requires GEMINI_API_KEY or "
                    "EMERGENT_LLM_KEY to be set."
                )
            gemini_model = model or self.model
            chat = LlmChat(
                api_key=self.api_key,
                session_id=f"theeyes-{uuid.uuid4().hex[:12]}",
                system_message=system_prompt,
            )
            chat.with_model("gemini", gemini_model)
            msg = UserMessage(
                text=user_text,
                file_contents=[ImageContent(b64)],
            )
            t0 = time.perf_counter()
            ok = False
            last_err: str | None = None
            try:
                raw = await chat.send_message(msg)
                ok = True
            except Exception as exc:  # noqa: BLE001
                last_err = repr(exc)
                raise
            finally:
                extra: dict[str, Any] = {
                    "provider": "gemini",
                    "model": gemini_model,
                    "routing_source": routing_source,
                }
                if used_fallback:
                    extra["fallback_from"] = "gemma"
                    extra["fallback_reason"] = fallback_reason
                provider_activity.record(
                    "garment-vision",
                    ok=ok,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    error=last_err,
                    extra=extra,
                )
            used_provider = "gemini"
            used_model = gemini_model

        # 4) Parse + sanitise. Eyes v3 (Gemma 4) may return a JSON array
        #    when the crop contains multiple garments; collapse to first.
        parsed = _coerce_single_garment(_extract_json(raw or ""))
        if not parsed.get("title") and parsed.get("name"):
            parsed["title"] = parsed["name"]
        if not parsed.get("title"):
            parsed["title"] = "Unnamed garment"
        parsed = _coerce_enums(parsed)
        parsed["provider_used"] = used_provider
        parsed["model_used"] = used_model
        if used_fallback:
            parsed["provider_fallback"] = {
                "from": "gemma",
                "to": "gemini",
                "reason": fallback_reason,
            }
        parsed["raw"] = {"preview": (raw or "")[:500]}
        logger.info(
            "The Eyes OK provider=%s model=%s routing=%s fallback=%s "
            "category=%s sub=%s item_type=%s",
            used_provider,
            used_model,
            routing_source,
            used_fallback,
            parsed.get("category"),
            parsed.get("sub_category"),
            parsed.get("item_type"),
        )
        return parsed

    # -------------------- multi-item outfit pipeline --------------------
    # -----------------------------------------------------------------
    # analyze_outfit helpers — extracted during Wave O.2 prep to drop
    # the parent function's cyclomatic complexity from 34 down to ~6.
    # Every helper is a thin, testable slice of a single lifecycle
    # phase (detect → short-circuit → filter → crop → matte → analyse).
    # -----------------------------------------------------------------
    @staticmethod
    def _build_fullframe_item(
        analysis: dict[str, Any],
        crop_bytes: bytes,
        *,
        label_hint: str | None = None,
        kind_hint: str | None = None,
        crop_mime: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Shape a single-item result dict covering the whole frame.

        Used by every fallback branch in :meth:`analyze_outfit` (photo
        looks already-cropped, no useful detections, every crop was
        rejected, every per-crop analysis failed) so the response
        contract stays identical no matter which path we took.
        """
        label = (
            label_hint
            or analysis.get("item_type")
            or analysis.get("sub_category")
            or "garment"
        )
        return {
            "label": label,
            "kind": kind_hint or "garment",
            "bbox": [0, 0, 1000, 1000],
            "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
            "crop_mime": crop_mime,
            "analysis": analysis,
        }

    async def _whole_image_matte(self, image_bytes: bytes) -> bytes | None:
        """rembg the full frame so already-cropped product photos save
        with a clean alpha channel instead of the raw upload.

        Returns ``None`` when ``AUTO_MATTE_CROPS`` is disabled or rembg
        errors out; callers fall back to the original JPEG bytes in
        that case.
        """
        if not settings.AUTO_MATTE_CROPS:
            logger.info("already-cropped matte: AUTO_MATTE_CROPS=False, skipping")
            return None
        try:
            from app.services import background_matting
            import time as _t

            t0 = _t.time()
            logger.info(
                "already-cropped matte: starting rembg on %d-byte image",
                len(image_bytes),
            )
            result = await background_matting.matte_crop(image_bytes)
            dt = _t.time() - t0
            if result:
                logger.info(
                    "already-cropped matte: SUCCESS in %.1fs (output %d bytes)",
                    dt,
                    len(result),
                )
            else:
                logger.warning(
                    "already-cropped matte: rembg returned None after %.1fs "
                    "(input %d bytes) — keeping original",
                    dt,
                    len(image_bytes),
                )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "already-cropped matte: rembg raised %s — keeping original",
                repr(exc)[:200],
            )
            return None

    async def _handle_already_cropped(
        self,
        image_bytes: bytes,
        detections: list[dict[str, Any]],
        language: str | None,
        *,
        think: bool = False,
    ) -> list[dict[str, Any]]:
        """Short-circuit for photos that are already tightly cropped.

        Runs matting and the single-image analyser SERIALLY (not
        ``asyncio.gather``) — concurrent rembg + Gemini on the
        3GB-container prod box has been observed silently OOM-killing
        the onnxruntime session. Latency cost is minimal; correctness
        matters more.
        """
        logger.info(
            "analyze_outfit: photo looks already-cropped "
            "(detections=%d); skipping crop pipeline",
            len(detections),
        )
        matted = await self._whole_image_matte(image_bytes)
        single = await self.analyze(
            image_bytes, language=language, think=think,
        )

        if matted:
            crop_bytes = matted
            crop_mime = "image/png"
        else:
            crop_bytes = image_bytes
            crop_mime = "image/jpeg"

        # Pick the LLM's classification first (most reliable on novelty
        # patterns / unusual fabrics). Fall back to the dominant
        # SegFormer detection if the analysis didn't yield a label.
        best_det: dict[str, Any] | None = None
        if detections:
            best_det = max(
                detections,
                key=lambda d: (
                    max(0, d["bbox"][2] - d["bbox"][0])
                    * max(0, d["bbox"][3] - d["bbox"][1])
                ),
            )
        label = (
            single.get("item_type")
            or single.get("sub_category")
            or (best_det.get("label") if best_det else None)
            or "garment"
        )
        kind = (best_det.get("kind") if best_det else None) or "garment"
        return [
            self._build_fullframe_item(
                single, crop_bytes,
                label_hint=label, kind_hint=kind, crop_mime=crop_mime,
            )
        ]

    @staticmethod
    def _filter_useful_detections(
        detections: list[dict[str, Any]], cap: int,
    ) -> list[dict[str, Any]]:
        """Drop near-full-frame detections and cap to ``max_items``.

        A single detection that covers ≥90% of the frame is treated as
        "analyse the whole photo" so we don't pay for an identical LLM
        call on a bbox-cropped copy.
        """
        useful: list[dict[str, Any]] = []
        for det in detections:
            bbox = det.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            ymin, xmin, ymax, xmax = bbox
            area = max(0, (ymax - ymin)) * max(0, (xmax - xmin))
            if area >= 1000 * 1000 * 0.9:
                continue
            useful.append(det)
        return useful[:cap]

    @staticmethod
    def _bbox_crop_useful(
        image_bytes: bytes, useful: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], bytes, str]]:
        """CPU-bound JPEG crop pass. Runs on a thread via
        :func:`asyncio.to_thread` from the caller.

        Also slices any SegFormer mask to the bbox and stashes it on
        the detection dict (``_mask_bbox``) so the matting step can
        intersect rembg's alpha with the per-class mask for cleaner
        garment separation.
        """
        from app.services import clothing_parser

        out: list[tuple[dict[str, Any], bytes, str]] = []
        try:
            from PIL import Image as _PILImage
            import io as _io

            _img = _PILImage.open(_io.BytesIO(image_bytes))
            img_size = _img.size  # (W, H)
        except Exception:  # noqa: BLE001
            img_size = None

        for det in useful:
            box_px = clothing_parser.bbox_to_pixels(image_bytes, det["bbox"])
            if not box_px:
                continue
            result = _crop_to_bbox(image_bytes, det["bbox"])
            if not result:
                continue
            crop_bytes, _xy = result
            mask = det.get("mask")
            if mask is not None and img_size is not None:
                mask_bbox = clothing_parser.slice_mask_to_bbox(
                    mask, img_size, box_px
                )
                if mask_bbox is not None:
                    det["_mask_bbox"] = mask_bbox
                    det["mask"] = None
            out.append((det, crop_bytes, "image/jpeg"))
        return out

    async def _matte_crops(
        self, raw_crops: list[tuple[dict[str, Any], bytes, str]],
    ) -> list[tuple[dict[str, Any], bytes, str]]:
        """Pipe each JPEG crop through rembg, optionally intersecting
        with the SegFormer per-class mask for sharper edges.

        Serialised because each rembg call holds the onnxruntime
        session — parallel invocations have been seen causing silent
        OOM kills in 3GB containers.
        """
        from app.services import background_matting
        from app.services import clothing_parser as _cp

        matted_crops: list[tuple[dict[str, Any], bytes, str]] = []
        for det, cbytes, mime in raw_crops:
            try:
                matted = await background_matting.matte_crop(cbytes)
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "auto-matte failed for %s: %s — keeping bbox crop",
                    det.get("label"),
                    repr(exc)[:120],
                )
                matted = None
            if not matted:
                matted_crops.append((det, cbytes, mime))
                continue
            seg_mask_bbox = det.get("_mask_bbox")
            if seg_mask_bbox is not None:
                try:
                    refined = _cp.apply_alpha_intersection(
                        matted, seg_mask_bbox
                    )
                    if refined:
                        matted = refined
                except Exception as exc:  # noqa: BLE001
                    logger.info(
                        "alpha intersection skipped for %s: %s",
                        det.get("label"),
                        repr(exc)[:120],
                    )
            det.pop("_mask_bbox", None)
            matted_crops.append((det, matted, "image/png"))
        return matted_crops

    async def _analyse_one_crop(
        self,
        det: dict[str, Any],
        crop_bytes: bytes,
        crop_mime: str,
        language: str | None,
        sem: asyncio.Semaphore,
        *,
        think: bool = False,
    ) -> dict[str, Any] | None:
        """Analyse a single crop + (optionally) reconstruct.

        Returns ``None`` when the per-crop analyse call fails so the
        caller can drop it silently — one bad crop shouldn't kill the
        whole outfit response.
        """
        async with sem:
            try:
                analysis = await self.analyze(
                    crop_bytes,
                    model=self.crop_model,
                    language=language,
                    think=think,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "crop analyze failed for label=%s: %s",
                    det.get("label"),
                    repr(exc)[:1500],
                )
                return None

            reconstruction_payload: dict[str, Any] | None = None
            try:
                from app.services.reconstruction import (
                    reconstruct,
                    should_reconstruct,
                )

                needs, reasons = should_reconstruct(analysis, det.get("bbox"))
                if needs:
                    reconstruction_payload = await reconstruct(
                        crop_bytes, analysis, reasons=reasons,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "reconstruction pipeline failed for label=%s: %s",
                    det.get("label"),
                    repr(exc)[:160],
                )
            return {
                "label": det.get("label") or "garment",
                "kind": det.get("kind") or "garment",
                "bbox": det.get("bbox"),
                "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
                "crop_mime": crop_mime,
                "analysis": analysis,
                "reconstruction": reconstruction_payload,
            }

    async def _analyse_crops(
        self,
        crops: list[tuple[dict[str, Any], bytes, str]],
        language: str | None,
        *,
        think: bool = False,
    ) -> list[dict[str, Any]]:
        """Run :meth:`_analyse_one_crop` over every crop with bounded
        concurrency, then strip unidentifiable results."""
        sem = asyncio.Semaphore(6)
        results = await asyncio.gather(
            *[
                self._analyse_one_crop(d, b, m, language, sem, think=think)
                for d, b, m in crops
            ]
        )
        items = [r for r in results if r]
        before_drop = len(items)
        items = [r for r in items if not _is_unidentifiable(r.get("analysis"))]
        if len(items) < before_drop:
            logger.info(
                "analyze_outfit: dropped %d unidentifiable item(s)",
                before_drop - len(items),
            )
        return items

    async def analyze_outfit(
        self, image_bytes: bytes, *, max_items: int | None = None,
        language: str | None = None,
        think: bool = False,
    ) -> list[dict[str, Any]]:
        """End-to-end multi-item pipeline.

        1. Gemini detects bounding boxes for every garment / accessory /
           jewelry piece.
        2. Each bbox is cropped server-side.
        3. Each crop is re-analysed in parallel by Gemini for the rich
           17-field form payload.
        4. Returned entries include the crop (as base64 JPEG) so the
           frontend can render a preview card per item and, when the
           user saves, persist the crop rather than the full outfit
           photo.

        Returns a list of dicts with shape::

            {
              "label": "oxford shirt",
              "kind": "garment",
              "bbox": [ymin, xmin, ymax, xmax],
              "crop_base64": "<base64 jpeg>",
              "crop_mime": "image/jpeg",
              "analysis": { ...GarmentAnalysis fields... }
            }

        When detection fails or yields nothing usable, we gracefully
        degrade to a single-item analysis of the original image.
        """
        # 1) Detect. Soft-fail to single-image analysis on error.
        try:
            detections = await self.detect_items(image_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "detect_items failed (%s); falling back to single analysis",
                repr(exc)[:160],
            )
            detections = []

        # 2) Fast-path: already-cropped product photo.
        if _looks_already_cropped(detections):
            return await self._handle_already_cropped(
                image_bytes, detections, language, think=think,
            )

        # 3) Filter + cap detections.
        cap = max_items if max_items is not None else self.max_items
        useful = self._filter_useful_detections(detections, cap)
        if not useful:
            single = await self.analyze(
                image_bytes, language=language, think=think,
            )
            return [self._build_fullframe_item(single, image_bytes)]

        # 4) Crop (CPU-bound; run on a worker thread).
        raw_crops = await asyncio.to_thread(
            self._bbox_crop_useful, image_bytes, useful,
        )

        # 5) Matte if enabled. Patch 8 (May 2026): when
        # ``settings.DEFER_REMBG_ON_ANALYZE`` is True (default), we
        # skip the synchronous serial rembg pass entirely and return
        # raw JPEG bbox crops. The /closet save endpoint queues the
        # matte as a BackgroundTask per item, identical to the
        # Phase-O.6 single-pass path. This is the dominant win for
        # the analyze latency budget (saves ~10-30s per crop, serial).
        defer_matte = (
            settings.DEFER_REMBG_ON_ANALYZE
            and settings.AUTO_MATTE_CROPS
            and bool(raw_crops)
        )
        if settings.AUTO_MATTE_CROPS and raw_crops and not defer_matte:
            crops = await self._matte_crops(raw_crops)
        else:
            crops = raw_crops
            if defer_matte:
                logger.info(
                    "analyze_outfit: deferring rembg for %d crop(s) to "
                    "post-save BackgroundTask (DEFER_REMBG_ON_ANALYZE=true)",
                    len(raw_crops),
                )

        if not crops:
            # Every crop was rejected (tiny / invalid bbox).
            single = await self.analyze(
                image_bytes, language=language, think=think,
            )
            return [self._build_fullframe_item(single, image_bytes)]

        # 6) Analyse each crop in parallel.
        items = await self._analyse_crops(crops, language, think=think)

        # 7) If every parallel call failed, fall back once.
        if not items:
            single = await self.analyze(image_bytes, think=think)
            return [self._build_fullframe_item(single, image_bytes)]

        # Patch 8 marker: flag every item so the /closet save endpoint
        # knows it must queue a rembg BackgroundTask for this crop
        # (the matte was intentionally skipped here to keep the
        # /analyze response under the 30s UX budget).
        if defer_matte:
            for it in items:
                it["defer_matte"] = True

        logger.info(
            "analyze_outfit OK detected=%d analysed=%d labels=%s",
            len(useful),
            len(items),
            [i["label"] for i in items][:8],
        )
        return items

    # ──────────────────────────────────────────────────────────────────
    # Phase O.6 — single-pass pipeline
    # ──────────────────────────────────────────────────────────────────
    async def analyze_outfit_one_pass(
        self,
        image_bytes: bytes,
        *,
        max_items: int | None = None,
        language: str | None = None,
        think: bool = False,
    ) -> list[dict[str, Any]]:
        """End-to-end multi-item pipeline in a SINGLE Eyes call.

        **RETIRED (May 2026) — benchmark / experimentation use only.**
        The CCP-Ninja benchmark (``/app/scripts/run_eyes_benchmark.py``)
        showed Gemini-2.5-Flash will not emit multi-garment arrays
        reliably: on all 30 test images it returned exactly one garment
        per call, collapsing recall to ~10%. Three prompt rewrites did
        not move the dial. The function is kept here so the benchmark
        script and any future fine-tuned-Eyes experiments can still
        invoke it, but production now always calls :meth:`analyze_outfit`
        (SegFormer + per-crop Eyes), which scores ~0.71 mean IoU and
        ~0.41 recall on the same dataset. The closet ``/analyze`` route
        no longer reads ``EYES_ONE_PASS``.

        Sends the original photo straight to ``analyze(one_pass=True)``,
        which returns either a single garment object (already-cropped
        product photo) or an array of garment objects (multi-item
        outfit). Each garment carries a ``region.bbox`` on a 0..1000
        normalised grid; we crop the original image to each bbox to
        produce per-garment JPEGs that the frontend can render
        immediately.

        Output shape matches :meth:`analyze_outfit` exactly so the
        ``/closet/analyze`` endpoint can swap implementations without
        any contract change visible to the frontend::

            {
              "label": "Oxford shirt",
              "kind": "garment",
              "bbox": [ymin, xmin, ymax, xmax],   # 0..1000 normalised
              "crop_base64": "<base64 jpeg>",
              "crop_mime": "image/jpeg",
              "analysis": { ...GarmentAnalysis fields, region stripped... },
              "reconstruction_advised": bool,     # NEW — frontend CTA hint
              "one_pass": True,                   # NEW — debug breadcrumb
            }
        """
        t0 = time.perf_counter()
        try:
            parsed = await self.analyze(
                image_bytes,
                language=language,
                think=think,
                one_pass=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "one_pass analyze() failed (%s) \u2014 falling back to legacy "
                "analyze_outfit so the user still gets a result.",
                repr(exc)[:200],
            )
            return await self.analyze_outfit(
                image_bytes,
                max_items=max_items,
                language=language,
                think=think,
            )

        # Eyes is allowed to return either a single object (already-cropped
        # shot) or an array of objects (multi-item outfit). Normalise.
        if isinstance(parsed, list):
            garments = parsed
        elif isinstance(parsed, dict):
            garments = [parsed]
        else:
            logger.warning(
                "one_pass got %s (expected dict or list) \u2014 falling back",
                type(parsed).__name__,
            )
            return await self.analyze_outfit(
                image_bytes,
                max_items=max_items,
                language=language,
                think=think,
            )

        # Cap at ``max_items`` (matches legacy contract).
        cap = max_items if max_items is not None else self.max_items
        if cap and len(garments) > cap:
            logger.info(
                "one_pass: trimming %d garments down to max_items=%d",
                len(garments), cap,
            )
            garments = garments[:cap]

        items: list[dict[str, Any]] = []
        for g in garments:
            region = g.get("region") if isinstance(g, dict) else None
            bbox: list[int]
            is_full_frame = False
            if isinstance(region, dict) and isinstance(region.get("bbox"), list):
                bbox_in = region["bbox"]
                # Defensive clamp: schema enforces 0..1000 but a fallback
                # provider (Gemini direct) may emit slightly out-of-range.
                try:
                    ymin, xmin, ymax, xmax = [
                        max(0, min(1000, int(v))) for v in bbox_in
                    ]
                    if ymax <= ymin:
                        ymax = min(1000, ymin + 1)
                    if xmax <= xmin:
                        xmax = min(1000, xmin + 1)
                    bbox = [ymin, xmin, ymax, xmax]
                except Exception:
                    bbox = [0, 0, 1000, 1000]
                is_full_frame = bool(region.get("is_full_frame"))
            else:
                # Model omitted region — treat the whole frame as the bbox.
                bbox = [0, 0, 1000, 1000]
                is_full_frame = True

            # Crop. Reuse the same helper the legacy pipeline uses so the
            # padding/area-floor rules stay consistent across both paths.
            crop_bytes: bytes
            if is_full_frame or bbox == [0, 0, 1000, 1000]:
                crop_bytes = image_bytes
            else:
                cropped = _crop_to_bbox(image_bytes, bbox)
                # ``_crop_to_bbox`` returns None when the bbox is degenerate
                # or below the min-area floor. In those cases we still want
                # an item record \u2014 just fall back to the full frame so
                # the user sees the original photo as the thumbnail.
                crop_bytes = cropped[0] if cropped else image_bytes

            # Strip ``region`` from the analysis dict so the persisted
            # closet item card doesn't carry coordinates the rest of the
            # app doesn't know about. Bbox lives on the item, not in
            # ``analysis``.
            analysis = {k: v for k, v in g.items() if k != "region"}

            label = (
                analysis.get("item_type")
                or analysis.get("sub_category")
                or analysis.get("title")
                or "garment"
            )

            items.append({
                "label": label,
                "kind": "garment",
                "bbox": bbox,
                "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
                "crop_mime": "image/jpeg",
                "analysis": analysis,
                # NEW \u2014 frontend reads this to decide whether to render
                # the opt-in "Repair photo" CTA (Phase 2 wires the actual
                # endpoint). Computed cheaply from existing analysis hints.
                "reconstruction_advised": _should_advise_reconstruction(
                    analysis, is_full_frame=is_full_frame,
                ),
                # Debug breadcrumb \u2014 dropped from prod responses by the
                # API layer if we want it hidden, but useful for the
                # diagnostic notebook and during the rollout.
                "one_pass": True,
            })

        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "analyze_outfit_one_pass OK garments=%d full_frame=%s elapsed_ms=%d "
            "labels=%s",
            len(items),
            any(i["bbox"] == [0, 0, 1000, 1000] for i in items),
            dt_ms,
            [i["label"] for i in items][:8],
        )
        return items


def _should_advise_reconstruction(
    analysis: dict[str, Any], *, is_full_frame: bool,
) -> bool:
    """Cheap heuristic for the opt-in "Repair photo" CTA.

    Mirrors the existing ``should_reconstruct`` logic in
    ``services/reconstruction.py`` but works off ONLY the data the
    one-pass result carries (no SegFormer mask, no bbox-edge analysis),
    so the answer is a hint to the user, not an authoritative
    "this needs reconstruction" verdict.

    Returns True when the analysed garment is reported as ``used`` and
    the condition is below ``good``, OR when the photo wasn't already
    a clean single-frame shot \u2014 i.e. exactly the cases where users
    historically benefited from the Nano-Banana studio reshoot.
    """
    state = (analysis.get("state") or "").lower()
    condition = (analysis.get("condition") or "").lower()
    if state == "used" and condition in {"bad", "fair"}:
        return True
    # If we cropped out of a busy multi-item photo, the user might prefer
    # a clean studio version for the closet thumbnail.
    if not is_full_frame:
        return True
    return False


def _build_vision_service() -> GarmentVisionService | None:
    """Instantiate the service if *any* supported provider is available."""
    want_hf = settings.GARMENT_VISION_PROVIDER == "hf"
    want_gemini_analyze = settings.GARMENT_VISION_PROVIDER == "gemini"
    has_hf = bool(settings.HF_TOKEN)
    has_gemini_chat = bool(settings.gemini_chat_key)
    if want_hf and not has_hf:
        logger.warning("Garment vision disabled: provider=hf but HF_TOKEN missing.")
        return None
    if want_gemini_analyze and not has_gemini_chat:
        logger.warning(
            "Garment vision disabled: provider=gemini but no Gemini chat key set "
            "(GEMINI_API_KEY / EMERGENT_LLM_KEY)."
        )
        return None
    try:
        return GarmentVisionService()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Garment vision init failed: %s", exc)
        return None


garment_vision_service = _build_vision_service()
