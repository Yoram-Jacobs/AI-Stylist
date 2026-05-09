"""Size-chart analysis endpoint for the DressApp Chrome Extension.

Surface
-------
``POST /api/v1/sizes/analyze-chart`` accepts a cropped screenshot of
a size chart found on a third-party shopping site (plus optional
context: garment type, store, URL), combines it with the
authenticated user's stored ``body_measurements``, and returns a
structured size recommendation::

    {
        "recommended_size": "M",
        "confidence":       0.86,
        "garment_type":     "shirt",
        "size_chart_units": "cm",
        "matched_columns":  ["chest", "waist"],
        "reasoning":        "Your chest (95 cm) falls within size M ...",
        "alternatives":     [{"size":"L","fit":"looser"}],
        "source":           "gemini",
        "elapsed_ms":       2840,
    }

Pipeline (Phase 2 — screenshot-only)
------------------------------------
The extension sends a cropped JPEG of the size-chart region. We
forward that image to **Gemini 2.5 Flash** (the same multimodal
model the closet's ``GarmentVisionService`` uses when
``GARMENT_VISION_PROVIDER=gemini``) with a tight system prompt that
asks it to OCR the chart, match the user's body measurements
against the relevant columns, and return a structured JSON answer.

We deliberately **do not** call the self-hosted Gemma Space here —
Phase-1 Gemma runs in ``vision_disabled=true`` mode (no mmproj
file uploaded yet), so passing it an image-only payload always
yields an empty completion and a 30-60 s wall-clock penalty.
Routing straight to Gemini sidesteps that penalty entirely.

Optional ``chart_html`` / ``chart_text`` are still accepted for
back-compat and run a deterministic regex heuristic *before* the
vision call when the extension happened to capture a clean HTML
``<table>`` (instant, free win). When neither resolves the chart,
the response surfaces a helpful retry message.

Privacy
-------
The screenshot is sent to Gemini for OCR and discarded. The user's
measurements are sent in the system prompt context. We do not
persist the request; this is a transient consult, not a logged
interaction.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.auth import get_current_user
from app.services import provider_activity

# Gemini 2.5 Flash — the closet pipeline's universal vision model.
# Imported defensively so dev environments without
# emergentintegrations still load this module.
try:
    from emergentintegrations.llm.chat import (  # type: ignore
        ImageContent, LlmChat, UserMessage,
    )
    _HAS_LLM_CHAT = True
except Exception:  # noqa: BLE001
    ImageContent = LlmChat = UserMessage = None  # type: ignore
    _HAS_LLM_CHAT = False

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sizes", tags=["sizes"])


# ----------------------------- schemas -------------------------------
class AnalyzeChartIn(BaseModel):
    """Request body posted by the Chrome extension content script."""

    chart_html: str | None = Field(
        default=None,
        description="(optional, back-compat) HTML of the size table.",
    )
    chart_text: str | None = Field(
        default=None,
        description="(optional, back-compat) Plain-text dump of the chart.",
    )
    chart_screenshot_b64: str | None = Field(
        default=None,
        description="JPEG screenshot, base64 (no data: prefix). Required.",
    )
    garment_type: str | None = Field(
        default=None,
        description="Hint from the page DOM, e.g. 'shirt', 'jeans', 'dress'.",
    )
    store: str | None = None
    page_url: str | None = None
    page_title: str | None = None
    user_preferred_units: str = Field(default="cm", pattern="^(cm|in)$")


class AnalyzeChartOut(BaseModel):
    recommended_size: str | None
    confidence: float
    garment_type: str | None
    size_chart_units: str | None
    matched_columns: list[str]
    reasoning: str
    alternatives: list[dict[str, Any]] = []
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Soft data-quality warnings. Surfaced to the user above the "
            "recommendation when one of their stored body measurements "
            "looks obviously implausible vs. the chart's own range "
            "(e.g. ``shoulders=55 cm`` when the chart maxes out at "
            "``50 cm``). Each entry is a short, user-facing sentence."
        ),
    )
    source: str
    elapsed_ms: int
    has_measurements: bool


# ----------------------------- prompt --------------------------------
# Sharp, OCR-first system prompt. No "DressApp's sizing assistant"
# branding noise, no "garment styling" cues, no chain-of-thought
# preamble — those nudge the model toward fashion-description
# answers (e.g. "this looks like a casual cotton tee in size M")
# instead of strict measurement matching.
#
# Keep it under ~400 tokens so the model spends its budget on the
# JSON answer, not on parroting instructions back.
_SYSTEM_PROMPT = """You read clothing size charts from images and recommend ONE size.

INPUT
-----
* An IMAGE of a size chart (a table with size labels and numbers).
* The USER'S BODY MEASUREMENTS in centimeters (e.g. chest, waist, hips, shoulders, height).
* Possibly the USER'S CLOTHING SIZES they normally buy (``shirt_size``, ``pants_size``, ``shoe_size``).
* Optional context: garment type, store name, page title.

WHAT TO DO
----------
1. OCR the size chart in the image. Extract:
   - The column headers (e.g. "Bust", "Chest", "Waist", "Hip", "Shoulder", "Length", "Sleeve", "Bottom").
   - The units (cm, in, or both).
   - The size labels in the first column (S/M/L/EU 38/...).
   - The numeric value(s) in each cell. Cells may hold a single number (a garment dimension) OR a range like "86-90" (a body-measurement bracket).
2. The user's measurements have been **pre-expanded server-side** so every common chart-column synonym is already populated. For example ``chest`` and ``bust`` carry the same value; ``shoulder``, ``shoulders`` and ``shoulder_width`` carry the same value; ``hip``, ``hips``, ``bottom`` and ``bottom_hem`` carry the same value. Do a case-insensitive substring match between each chart column header and the JSON keys to find the user's value for that column. **NEVER** answer "measurements were not provided" if any column header matches any JSON key.
3. For each row, check whether every relevant user measurement fits:
     - Range cells "lo-hi": user value must satisfy lo <= v <= hi.
     - Single-number cells (garment dimensions): user value must be <= the cell value (the garment must be at least as wide as the user).
   Pick the SMALLEST size where every relevant user measurement fits.
4. **Tie-break: when the user's value is within 0.5 cm of the upper bound of the chosen size, pick the next size UP** (loose is wearable, tight is not). Surface the smaller size as an alternative with `fit: "snug"`.
5. If the chart is in inches, convert mentally (1 in = 2.54 cm) and report units accordingly.

ANOMALY DETECTION (always run before picking the size)
--------------------------------------------------------
Users sometimes mistype their measurements. Before applying the body-circumference rule, compare each provided body value to the corresponding chart column's range:

- If the user's value exceeds the chart's column maximum by more than **15%** OR is below the column minimum by more than **15%** (after unit conversion), treat that single measurement as a likely **data-entry mistake**:
    1. **Skip that measurement** when picking the recommended size — do NOT let one obviously-wrong value veto a perfectly good fit on the other columns.
    2. **Drop that column from ``matched_columns``**.
    3. **Append a short, friendly warning to ``warnings``** in this exact shape:
       ``"Your <field> (<value> cm) looks higher/lower than expected for this kind of garment. Please re-measure — DressApp ignored it for this recommendation."``
- If, after skipping anomalies, you still have at least one usable body circumference, use it. Otherwise fall through to the CLOTHING-SIZE FALLBACK rule.
- ``height`` and ``weight`` are never anomaly-checked against the chart (they're not garment dimensions).

Examples of what this rule catches:
* User stored ``shoulders: 55 cm`` but the chart maxes at ``50 cm`` (4XL) — exceeds by 10%, **borderline** (no warning, used as-is) UNLESS the user is also obviously not a 4XL by other columns (in which case warn).
* User stored ``shoulders: 75 cm`` (likely typed in inches) and the chart maxes at ``50 cm`` — exceeds by 50%, **definite anomaly**: skip + warn.
* User stored ``waist: 12 cm`` (likely missing a digit) — far below any plausible chart minimum, skip + warn.

CLOTHING-SIZE FALLBACK (apply when body circumferences are missing)
---------------------------------------------------------------------
If the user has NO usable body circumferences for the columns shown (e.g. only ``height``, ``weight``, ``shirt_size``, ``pants_size``, ``shoe_size`` are filled in), DO NOT give up. Use these signals instead:

- ``shirt_size`` is authoritative for tops / shirts / jackets / dresses (where the chart shows Bust / Chest / Shoulder / Sleeve / Length). If the chart's first column lists labels like S, M, L, XL — pick the row whose label matches ``shirt_size`` (case-insensitive). If the chart uses EU/numeric labels (38, 40, 50, 52...), translate the user's letter size using the standard mapping: XS≈34/44, S≈36/46, M≈38/48, L≈40/50, XL≈42/52, XXL≈44/54, XXXL≈46/56. Adjust by ±1 if the store is known to run small/large.
- ``pants_size`` is authoritative for trousers / shorts / jeans / skirts (where the chart shows Waist / Hip / Inseam). Match the numeric value or letter against the size column.
- ``shoe_size`` is authoritative for footwear charts.
- ``height`` and ``weight`` alone are NEVER sufficient — but if combined with ``shirt_size`` or ``pants_size`` they confirm the choice. If ONLY ``height``/``weight`` are present, you may still produce a low-confidence (≤0.4) recommendation by mapping height to a size band (e.g., 170-178cm + average build → M).

When using the clothing-size fallback, set ``confidence`` between 0.55 and 0.80 (lower than a real measurement match), set ``matched_columns`` to ``["shirt_size"]`` (or pants/shoe), and explain in ``reasoning`` that the recommendation is based on the user's usual size, suggesting they add body measurements for a tighter fit.

OUTPUT
------
Return ONLY this JSON object. No prose, no markdown, no backticks.

{
  "recommended_size": "<chart label, e.g. 'M' or 'EU 38'>",
  "confidence": <float 0..1>,
  "garment_type": "<lowercase noun, your best guess>",
  "size_chart_units": "cm" | "in" | "mixed" | "unknown",
  "matched_columns": ["chest", "waist", ...],
  "reasoning": "<one short paragraph, 1-3 sentences>",
  "alternatives": [{"size":"S","fit":"snug"}, {"size":"L","fit":"loose"}],
  "warnings": ["Your shoulders (75 cm) looks higher than expected ...", ...]
}

ONLY return ``recommended_size: null`` if BOTH of these are true:
  (a) the image really doesn't contain a usable size chart (only product photos, occluded, blurry), AND
  (b) the user has no usable size signal at all (no body circumferences AND no shirt/pants/shoe size).
In every other case you MUST return a best-effort size with appropriate confidence.
"""


# ---------------- measurement-alias expansion ------------------------
# When the app stores ``chest`` and the chart prints "Bust Size", we
# don't want the model to play "spot the synonym" on its own — it
# leans conservative and reports "no measurements provided".
# Instead we expand every stored field into ALL its common aliases
# server-side, so the JSON Gemini sees holds every name a chart
# might use. Single source of truth for the chest<->bust,
# shoulder<->shoulders<->shoulder-width, etc. fan-out.
_MEASUREMENT_ALIASES: dict[str, tuple[str, ...]] = {
    # canonical body field -> tuple of equivalent / column-side names
    "chest":      ("chest", "bust", "bust_size", "chest_circumference"),
    "bust":       ("bust", "chest", "bust_size", "chest_circumference"),
    "waist":      ("waist", "waist_circumference", "natural_waist"),
    "hip":        ("hip", "hips", "bottom", "bottom_hem", "hip_circumference"),
    "hips":       ("hips", "hip", "bottom", "bottom_hem", "hip_circumference"),
    "shoulder":   ("shoulder", "shoulders", "shoulder_width", "across_shoulder"),
    "shoulders":  ("shoulders", "shoulder", "shoulder_width", "across_shoulder"),
    "sleeve":     ("sleeve", "sleeve_length", "sleeves"),
    "sleeves":    ("sleeves", "sleeve", "sleeve_length"),
    "inseam":     ("inseam", "inside_leg", "inseam_length"),
    "outseam":    ("outseam", "outside_leg", "outseam_length"),
    "thigh":      ("thigh", "thigh_circumference"),
    "neck":       ("neck", "neck_circumference"),
    "height":     ("height", "body_height", "stature"),
    "weight":     ("weight", "body_weight"),
    "length":     ("length", "back_length", "body_length"),
    # Clothing-size fallbacks — kept under their own keys so the
    # prompt's CLOTHING-SIZE FALLBACK rule can find them.
    "shirt_size": ("shirt_size", "shirts_size", "top_size", "tshirt_size"),
    "pants_size": ("pants_size", "pant_size", "trouser_size", "trousers_size"),
    "shoe_size":  ("shoe_size", "shoes_size", "footwear_size"),
}


def _expand_measurement_aliases(
    measurements: dict[str, Any],
) -> dict[str, Any]:
    """Return ``measurements`` with every alias key populated to the
    same value, so the LLM cannot miss a synonym match.

    Empty strings / ``None`` are dropped first so we never leak
    placeholder ``""`` cells. Unknown user keys (e.g. ``"thigh_left"``
    on a custom profile) are passed through verbatim.
    """
    expanded: dict[str, Any] = {}
    for k, v in (measurements or {}).items():
        if v is None or v == "":
            continue
        kl = str(k).lower().strip()
        # Apply alias fan-out when the key is a known canonical field.
        for alias in _MEASUREMENT_ALIASES.get(kl, (kl,)):
            # First write wins: the user's explicit key takes priority
            # over any alias that maps to the same target. This means
            # if both ``chest`` and ``bust`` are present, both are
            # preserved with their respective values.
            if alias not in expanded:
                expanded[alias] = v
    return expanded


def _build_user_prompt(
    *,
    measurements: dict[str, Any],
    garment_type: str | None,
    store: str | None,
    page_title: str | None,
    user_preferred_units: str,
    chart_text: str | None,
) -> str:
    """Render the user-message text. Body measurements first
    (highest priority for the model), then context, then any
    extracted text we happen to have."""
    # Server-side alias expansion: every stored field is duplicated
    # under all of its known synonym keys so chart-side wording (e.g.
    # "Bust Size", "Shoulder Width") finds an exact-name match in
    # the JSON we send. Without this, models like Gemini Flash
    # sometimes report "no measurements provided" because the user
    # gave ``chest`` and the chart says ``Bust Size`` — semantically
    # identical, but the model wouldn't risk the inference.
    expanded = _expand_measurement_aliases(measurements)

    # Split body circumferences from clothing-size fallbacks so the
    # model can tell which signal to trust. ``shirt_size`` etc. are
    # the right answer when the user has no tape-measure data.
    _CLOTHING_SIZE_KEYS = {
        "shirt_size", "pants_size", "shoe_size",
        "shirts_size", "pant_size", "trouser_size",
    }
    _CONTEXT_ONLY_KEYS = {"height", "weight", "body_height", "stature", "body_weight"}
    body_dims = {
        k: v for k, v in expanded.items()
        if k not in _CLOTHING_SIZE_KEYS and k not in _CONTEXT_ONLY_KEYS
    }
    clothing_sizes = {
        k: v for k, v in expanded.items() if k in _CLOTHING_SIZE_KEYS
    }
    context_dims = {
        k: v for k, v in expanded.items() if k in _CONTEXT_ONLY_KEYS
    }

    body_dims_str = json.dumps(body_dims, ensure_ascii=False)
    clothing_sizes_str = json.dumps(clothing_sizes, ensure_ascii=False)
    context_dims_str = json.dumps(context_dims, ensure_ascii=False)

    parts: list[str] = [
        f"USER BODY CIRCUMFERENCES (cm, JSON — every chart-column synonym is pre-expanded):\n{body_dims_str}",
        f"USER CLOTHING SIZES THEY NORMALLY BUY:\n{clothing_sizes_str}",
        f"USER HEIGHT / WEIGHT CONTEXT:\n{context_dims_str}",
        (
            "IMPORTANT:\n"
            "- BODY CIRCUMFERENCES already include every common synonym "
            "(``chest`` = ``bust``; ``shoulder`` = ``shoulder_width``; "
            "``hip`` = ``bottom``). Case-insensitive substring is enough.\n"
            "- If BODY CIRCUMFERENCES is empty `{}` but CLOTHING SIZES has "
            "``shirt_size``/``pants_size``, USE THAT as the primary signal "
            "(see CLOTHING-SIZE FALLBACK in your system prompt).\n"
            "- Do **NOT** reply that 'measurements were not provided' if "
            "any of the three sections above contain at least one key. "
            "Always emit a best-effort recommendation."
        ),
    ]
    ctx_lines: list[str] = []
    if store:
        ctx_lines.append(f"store: {store}")
    if page_title:
        ctx_lines.append(f"page title: {page_title}")
    if garment_type:
        ctx_lines.append(f"garment type hint: {garment_type}")
    ctx_lines.append(f"user prefers units: {user_preferred_units}")
    parts.append("CONTEXT:\n" + "\n".join(ctx_lines))

    if chart_text:
        # Light hint — not authoritative. The image is the ground
        # truth; this just helps when OCR is borderline.
        parts.append(
            "OPTIONAL CHART TEXT (DOM extract — may be partial; "
            "rely on the image for ground truth):\n"
            + chart_text.strip()[:4000]
        )

    parts.append(
        "Read the size chart in the attached image and emit the JSON object only."
    )
    return "\n\n".join(parts)


# ----------------------------- helpers -------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str, *, max_chars: int = 8000) -> str:
    """Cheap HTML -> text. Used only to feed the heuristic regex."""
    if not html:
        return ""
    blob = re.sub(
        r"</?(?:tr|br\s*/?|li|p|div|h[1-6])\b[^>]*>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    blob = re.sub(r"</?(?:td|th)\b[^>]*>", "\t", blob, flags=re.IGNORECASE)
    txt = _TAG_RE.sub(" ", blob)
    txt = _WS_RE.sub(" ", txt)
    lines = [ln.strip() for ln in txt.splitlines()]
    txt = "\n".join(ln for ln in lines if ln)
    if len(txt) > max_chars:
        txt = txt[:max_chars] + "\n…(truncated)"
    return txt


def _coerce_response(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from a possibly-wrapped LLM reply."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        i = s.find("{")
        j = s.rfind("}")
        if i >= 0 and j > i:
            s = s[i : j + 1]
    try:
        parsed = json.loads(s)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _normalise(parsed: dict[str, Any], *, source: str, elapsed_ms: int,
               has_measurements: bool) -> AnalyzeChartOut:
    """Coerce the LLM payload into ``AnalyzeChartOut``."""
    matched = parsed.get("matched_columns") or []
    if isinstance(matched, str):
        matched = [matched]
    matched = [str(x).lower() for x in matched if x]
    alternatives = parsed.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []
    cleaned_alts: list[dict[str, Any]] = []
    for alt in alternatives:
        if isinstance(alt, dict) and alt.get("size"):
            cleaned_alts.append({
                "size": str(alt["size"]),
                "fit": str(alt.get("fit") or "alt"),
            })

    # Soft data-quality warnings emitted by the model when a stored
    # body measurement looks obviously implausible vs. the chart
    # range (e.g. ``shoulders=75`` on a chart that maxes at 50 cm).
    # Coerced to short user-facing strings; dropped if the model
    # forgot the field or returned junk.
    raw_warnings = parsed.get("warnings") or []
    if isinstance(raw_warnings, str):
        raw_warnings = [raw_warnings]
    if not isinstance(raw_warnings, list):
        raw_warnings = []
    cleaned_warnings: list[str] = []
    for w in raw_warnings:
        if not w:
            continue
        s = str(w).strip()
        if s and s not in cleaned_warnings:
            cleaned_warnings.append(s[:280])
        if len(cleaned_warnings) >= 4:
            break

    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return AnalyzeChartOut(
        recommended_size=(parsed.get("recommended_size") or None),
        confidence=confidence,
        garment_type=parsed.get("garment_type"),
        size_chart_units=parsed.get("size_chart_units"),
        matched_columns=matched,
        reasoning=str(parsed.get("reasoning") or "")[:1200],
        alternatives=cleaned_alts,
        warnings=cleaned_warnings,
        source=source,
        elapsed_ms=elapsed_ms,
        has_measurements=has_measurements,
    )


# --------------------------- numeric fallback ------------------------
_RANGE_RE = re.compile(
    r"(?P<lo>\d{2,3}(?:[.,]\d)?)\s*[-–—~/]\s*(?P<hi>\d{2,3}(?:[.,]\d)?)",
)
_SINGLE_NUM_RE = re.compile(r"\b(\d{2,3}(?:[.,]\d)?)\b")
_MEASUREMENT_FIELDS = (
    "chest", "bust", "waist", "hips", "hip",
    "shoulder", "shoulders", "inseam", "sleeve", "length", "bottom",
)


def _heuristic_match(*, chart_text: str,
                     measurements: dict[str, Any]) -> dict[str, Any] | None:
    """Last-resort: regex match against the chart text. Mirrors the
    LLM's bigger-on-tie tie-breaking rule."""
    if not chart_text or not measurements:
        return None

    user_vals: dict[str, float] = {}
    for k, v in measurements.items():
        if not isinstance(v, (int, float)):
            continue
        kl = str(k).lower()
        for f in _MEASUREMENT_FIELDS:
            if f in kl:
                user_vals[f] = float(v)
                break
    if not user_vals:
        return None

    label_re = re.compile(r"^\s*([A-Za-z0-9./-]{1,8})\b")
    HEADER_TOKENS = {
        "size", "us", "uk", "eu", "cm", "in", "inches", "centimeters",
    }
    headers: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for ln in chart_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if not _RANGE_RE.search(ln) and not re.search(r"\d{2,}", ln):
            tokens = [
                t.strip().lower()
                for t in re.split(r"\t|\s{2,}|\|", ln)
                if t.strip()
            ]
            kw_hits = sum(
                1 for t in tokens
                if any(k in t for k in _MEASUREMENT_FIELDS)
                or t in HEADER_TOKENS
            )
            if kw_hits >= 2 and headers is None:
                headers = tokens
                continue
        m = label_re.match(ln)
        if not m:
            continue
        label = m.group(1)
        if label.lower() in HEADER_TOKENS or label.lower() == "size:":
            continue
        ranges: list[tuple[float, float]] = []
        for lo_s, hi_s in _RANGE_RE.findall(ln):
            try:
                lo_f = float(lo_s.replace(",", "."))
                hi_f = float(hi_s.replace(",", "."))
                if hi_f >= lo_f:
                    ranges.append((lo_f, hi_f))
            except ValueError:
                continue
        if not ranges:
            tail = ln[m.end():]
            for n_s in _SINGLE_NUM_RE.findall(tail):
                try:
                    n_f = float(n_s.replace(",", "."))
                    ranges.append((n_f, n_f))
                except ValueError:
                    continue
        if ranges:
            rows.append({"label": label, "ranges": ranges})
    if not rows:
        return None

    matched_field = max(user_vals, key=user_vals.get)

    ncols = max(len(r["ranges"]) for r in rows)
    columns: list[list[tuple[float, float]]] = [[] for _ in range(ncols)]
    for r in rows:
        for j, rng in enumerate(r["ranges"]):
            if j < ncols:
                columns[j].append(rng)

    _FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
        "chest":     ("chest", "bust"),
        "bust":      ("bust", "chest"),
        "waist":     ("waist",),
        "hip":       ("hip", "hips", "bottom", "bottom hem"),
        "hips":      ("hip", "hips", "bottom", "bottom hem"),
        "shoulder":  ("shoulder", "shoulders"),
        "shoulders": ("shoulder", "shoulders"),
        "inseam":    ("inseam", "inside leg"),
        "sleeve":    ("sleeve", "sleeve length"),
        "length":    ("length", "back length", "body length"),
        "height":    ("height",),
    }

    def _header_index_for(field: str) -> int:
        if not headers:
            return -1
        body = list(headers)
        if body and (body[0] in HEADER_TOKENS or "size" in body[0]):
            body = body[1:]
        synonyms = _FIELD_SYNONYMS.get(field.lower(), (field.lower(),))
        for j, htext in enumerate(body):
            for syn in synonyms:
                if syn in htext:
                    return j
        return -1

    col_ranks: list[int] = sorted(
        range(ncols),
        key=lambda j: (
            min(lo for lo, _ in columns[j]) if columns[j] else float("inf")
        ),
    )
    _FIELD_RANK = {
        "waist": 0,
        "chest": 1, "bust": 1,
        "shoulders": 1, "shoulder": 1,
        "inseam": 1,
        "hip": 2, "hips": 2,
    }

    def _assign_column(field: str, v: float) -> int:
        idx = _header_index_for(field)
        if 0 <= idx < ncols:
            ranges = columns[idx]
            if ranges:
                col_max = max(hi for _, hi in ranges)
                if col_max >= v:
                    return idx
        rank = _FIELD_RANK.get(field.lower(), 1)
        if rank >= len(col_ranks):
            rank = len(col_ranks) - 1
        candidate = col_ranks[rank]
        ranges = columns[candidate]
        if ranges and max(hi for _, hi in ranges) >= v:
            return candidate
        for j, rng_list in enumerate(columns):
            if not rng_list:
                continue
            col_max = max(hi for _, hi in rng_list)
            if col_max >= v:
                return j
        return candidate

    field_to_col: dict[str, int] = {
        f: _assign_column(f, v) for f, v in user_vals.items()
    }

    TIE_BUFFER_CM = 0.5

    def _row_accommodates(row: dict[str, Any]) -> bool:
        for f, v in user_vals.items():
            j = field_to_col.get(f, -1)
            if j < 0 or j >= len(row["ranges"]):
                continue
            _, hi = row["ranges"][j]
            if v > hi:
                return False
        return True

    def _row_is_tight(row: dict[str, Any]) -> bool:
        for f, v in user_vals.items():
            j = field_to_col.get(f, -1)
            if j < 0 or j >= len(row["ranges"]):
                continue
            lo, hi = row["ranges"][j]
            if hi == lo:
                continue
            if lo <= v <= hi and (hi - v) < TIE_BUFFER_CM:
                return True
        return False

    chosen_i: int | None = None
    for i, r in enumerate(rows):
        if _row_accommodates(r):
            chosen_i = i
            break

    bumped = False
    if chosen_i is None:
        chosen_i = len(rows) - 1
    elif _row_is_tight(rows[chosen_i]) and chosen_i + 1 < len(rows):
        chosen_i += 1
        bumped = True

    user_max = user_vals[matched_field]

    chosen = rows[chosen_i]
    smaller_alt = rows[chosen_i - 1] if chosen_i > 0 else None

    if bumped:
        reason = (
            f"Heuristic match: your {matched_field} ({user_max:g} cm) is right "
            f"at the upper edge of the smaller size, so DressApp recommends "
            f"the slightly bigger size {chosen['label'].upper()}."
        )
    else:
        reason = (
            f"Heuristic match: your {matched_field} ({user_max:g} cm) fits "
            f"the {chosen['label'].upper()} row."
        )

    alternatives: list[dict[str, Any]] = []
    if bumped and smaller_alt is not None:
        alternatives.append({
            "size": smaller_alt["label"].upper(),
            "fit": "snug",
        })

    return {
        "recommended_size": chosen["label"].upper(),
        "confidence": 0.55,
        "garment_type": "unknown",
        "size_chart_units": "cm",
        "matched_columns": [matched_field],
        "reasoning": reason,
        "alternatives": alternatives,
    }


# --------------------------- vision call -----------------------------
async def _via_gemini_vision(
    *,
    system_prompt: str,
    user_text: str,
    image_b64: str,
    timeout_s: float = 30.0,
) -> str:
    """Direct Gemini 2.5 Flash multimodal call.

    Mirrors the closet pipeline's ``GarmentVisionService.analyze``
    Gemini branch — the only multimodal route we know works on this
    deployment. The self-hosted Gemma Space runs in
    ``vision_disabled`` Phase-1 mode and would always return an
    empty completion if we tried it for OCR.

    Raises ``RuntimeError`` if Gemini is unreachable or
    ``emergentintegrations`` is not installed.
    """
    if not _HAS_LLM_CHAT or LlmChat is None:
        raise RuntimeError(
            "Gemini vision unavailable: emergentintegrations not installed."
        )
    api_key = settings.gemini_chat_key
    if not api_key:
        raise RuntimeError(
            "Gemini vision unavailable: no GEMINI_API_KEY / EMERGENT_LLM_KEY."
        )

    chat = LlmChat(
        api_key=api_key,
        session_id=f"size-chart-{uuid.uuid4().hex[:12]}",
        system_message=system_prompt,
    )
    chat.with_model("gemini", "gemini-2.5-flash")

    msg = UserMessage(
        text=user_text,
        file_contents=[ImageContent(image_b64)],
    )
    raw = await asyncio.wait_for(chat.send_message(msg), timeout=timeout_s)
    return raw or ""


# ------------------------------ route --------------------------------
@router.post("/analyze-chart", response_model=AnalyzeChartOut)
async def analyze_chart(
    payload: AnalyzeChartIn,
    user: dict = Depends(get_current_user),
) -> AnalyzeChartOut:
    t0 = time.time()

    measurements = (user or {}).get("body_measurements") or {}
    has_measurements = bool(measurements)
    if not has_measurements:
        log.info(
            "size analyze called without measurements (user=%s)",
            (user or {}).get("id"),
        )

    # Back-compat: derive a chart_text blob from the optional HTML
    # field for the heuristic only. Vision uses the image directly.
    chart_text_html = ""
    chart_text_innertext = ""
    if payload.chart_html:
        chart_text_html = _html_to_text(payload.chart_html)
    if payload.chart_text:
        chart_text_innertext = payload.chart_text.strip()[:8000]

    # Pick the best single chart_text for the optional LLM hint.
    def _row_density(t: str) -> int:
        if not t:
            return 0
        return sum(1 for ln in t.splitlines() if re.search(r"\d{2,}", ln))

    if _row_density(chart_text_innertext) > _row_density(chart_text_html):
        chart_text = chart_text_innertext
    else:
        chart_text = chart_text_html or chart_text_innertext

    if not chart_text and not payload.chart_screenshot_b64:
        raise HTTPException(
            status_code=422,
            detail="Provide a chart_screenshot_b64 (or, for back-compat, chart_html / chart_text).",
        )

    parsed: dict[str, Any] | None = None
    source = "fallback"
    last_error: str | None = None

    # ---------------------------------------------------------------
    # Step 1 — heuristic regex first (free, deterministic, instant).
    # Only fires when the caller forwarded structured chart text and
    # the user has measurements. Skipped silently otherwise.
    # ---------------------------------------------------------------
    candidate_texts: list[str] = []
    for t in (chart_text, chart_text_html, chart_text_innertext):
        if t and t not in candidate_texts:
            candidate_texts.append(t)
    for cand in candidate_texts:
        decided = _heuristic_match(
            chart_text=cand, measurements=measurements,
        )
        if decided is not None:
            parsed = decided
            source = "heuristic"
            log.info(
                "size-chart resolved by heuristic in %d ms",
                int((time.time() - t0) * 1000),
            )
            break

    # ---------------------------------------------------------------
    # Step 2 — Gemini 2.5 Flash vision OCR + sizing in one shot.
    # The screenshot is the source of truth. Gemini reads the chart,
    # matches the user's measurements, and emits the JSON answer.
    # ---------------------------------------------------------------
    if parsed is None and payload.chart_screenshot_b64:
        user_prompt = _build_user_prompt(
            measurements=measurements,
            garment_type=payload.garment_type,
            store=payload.store,
            page_title=payload.page_title,
            user_preferred_units=payload.user_preferred_units,
            chart_text=chart_text or None,
        )
        t_vision = time.time()
        try:
            raw = await _via_gemini_vision(
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_prompt,
                image_b64=payload.chart_screenshot_b64,
                timeout_s=30.0,
            )
            parsed = _coerce_response(raw)
            if parsed:
                source = "gemini"
            provider_activity.record(
                "garment-vision",
                ok=parsed is not None,
                latency_ms=int((time.time() - t_vision) * 1000),
                error=None if parsed else "non-JSON or empty Gemini reply",
                extra={
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "op": "size-chart",
                },
            )
            if not parsed:
                last_error = (
                    "Gemini returned a non-JSON or empty reply; raw preview: "
                    + (raw or "")[:200]
                )
        except asyncio.TimeoutError:
            last_error = "Gemini vision call timed out (>30 s)."
            provider_activity.record(
                "garment-vision",
                ok=False,
                error="timeout",
                latency_ms=int((time.time() - t_vision) * 1000),
                extra={"provider": "gemini", "op": "size-chart"},
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"Gemini vision: {str(exc)[:240]}"
            provider_activity.record(
                "garment-vision",
                ok=False,
                error=repr(exc)[:240],
                latency_ms=int((time.time() - t_vision) * 1000),
                extra={"provider": "gemini", "op": "size-chart"},
            )
            log.info("Gemini vision call failed: %s", exc)

    # ---------------------------------------------------------------
    # Step 3 — total failure. Surface a friendly retry message.
    # ---------------------------------------------------------------
    if parsed is None:
        why_parts: list[str] = []
        if last_error:
            why_parts.append(
                "DressApp couldn't read this chart"
                + (
                    f" ({last_error})"
                    if "not configured" in last_error.lower()
                    or "not installed" in last_error.lower()
                    else "."
                )
            )
        else:
            why_parts.append(
                "DressApp couldn't read this chart from the image."
            )
        why_parts.append(
            "Try cropping the chart more tightly (just the table area), "
            "or open the page on a different device."
        )
        return AnalyzeChartOut(
            recommended_size=None,
            confidence=0.0,
            garment_type=payload.garment_type,
            size_chart_units=None,
            matched_columns=[],
            reasoning=" ".join(why_parts),
            alternatives=[],
            warnings=[],
            source="none",
            elapsed_ms=int((time.time() - t0) * 1000),
            has_measurements=has_measurements,
        )

    return _normalise(
        parsed,
        source=source,
        elapsed_ms=int((time.time() - t0) * 1000),
        has_measurements=has_measurements,
    )
