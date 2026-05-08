"""Size-chart analysis endpoint for the DressApp Chrome Extension.

Surface
-------
``POST /api/v1/sizes/analyze-chart`` accepts a payload representing a
size chart found on a third-party shopping site (HTML, plain text, or
a screenshot) plus optional context (garment type, store name, URL),
combines it with the authenticated user's stored ``body_measurements``,
and returns a structured size recommendation::

    {
        "recommended_size": "M",
        "confidence":       0.86,
        "garment_type":     "shirt",
        "size_chart_units": "cm",
        "matched_columns":  ["chest", "waist"],
        "reasoning":        "Your chest (95 cm) falls within size M ...",
        "alternatives":     [{"size":"L","fit":"looser"}],
        "source":           "gemma" | "qwen" | "fallback",
        "elapsed_ms":       2840,
    }

Routing
-------
Step 1 — try the user's active **Eyes** provider (resolved through
``eyes_override`` so the Profile toggle works here too).
  * If Eyes is set to ``gemma`` and ``EYES_GEMMA_SPACE_URL`` is wired,
    we call the self-hosted Gemma-4 endpoint with a *size-chart-
    specific* system prompt — different from the closet-analyzer one.
    Gemma-4 has decent OCR, so we forward the screenshot when the
    HTML doesn't contain a parseable table.
  * Any failure (timeout / 5xx / non-JSON) -> fall through to step 2.

Step 2 — fall back to the existing Qwen / DashScope text path. Sends
the same prompt + chart text (no image; Qwen-VL would work but the
text path is faster and the chart is fundamentally tabular text).

Step 3 — last-resort heuristic. If both LLMs fail, do a numeric
match against the chart text using simple regex extraction. Lower
confidence but never returns an error to the user.

Privacy
-------
The chart HTML is forwarded to whichever LLM is active. The user's
measurements are sent in the system prompt context. We do **not**
persist the request; this is a transient consult, not a logged
interaction.
"""
from __future__ import annotations

import json
import logging
import re
import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.auth import get_current_user
from app.services.eyes_override import get_active_provider
from app.services.garment_vision import _call_gemma_space
from app.services import provider_activity

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sizes", tags=["sizes"])


# ----------------------------- schemas -------------------------------
class AnalyzeChartIn(BaseModel):
    """Request body posted by the Chrome extension content script."""

    chart_html: str | None = Field(
        default=None,
        description="Raw HTML of the size table (preferred when present).",
    )
    chart_text: str | None = Field(
        default=None,
        description="Plain-text fallback if the page didn't expose a table.",
    )
    chart_screenshot_b64: str | None = Field(
        default=None,
        description="JPEG screenshot, base64 (no data: prefix). OCR fallback.",
    )
    garment_type: str | None = Field(
        default=None,
        description="Hint from the page DOM, e.g. 'shirt', 'jeans', 'dress'.",
    )
    store: str | None = None
    page_url: str | None = None
    page_title: str | None = None
    # Allow the extension to override units the user prefers in the
    # response (e.g. for US stores that ship in inches but the user
    # measured in cm). Server still passes the chart's native units to
    # the LLM; this just hints the response narrative.
    user_preferred_units: str = Field(default="cm", pattern="^(cm|in)$")


class AnalyzeChartOut(BaseModel):
    recommended_size: str | None
    confidence: float
    garment_type: str | None
    size_chart_units: str | None
    matched_columns: list[str]
    reasoning: str
    alternatives: list[dict[str, Any]] = []
    source: str
    elapsed_ms: int
    has_measurements: bool


# ----------------------------- prompts -------------------------------
_SYSTEM_PROMPT = """You are DressApp's sizing assistant.

You are given:
  * A clothing size chart from a third-party shopping site. It can
    arrive as **HTML**, as **plain text**, or as a **screenshot image**
    that you must OCR. The screenshot may be a tightly-cropped chart
    image OR a full browser viewport — in the latter case ignore the
    surrounding product photos, navigation, ads, and reviews and focus
    only on the obvious tabular region with size labels (S/M/L/EU 38…)
    and numeric ranges (cm or in).
  * The user's body measurements (chest / bust, waist, hips, etc.).
  * Optional metadata: garment type hint, store name, page title.

Reason step-by-step **internally** before answering:
  1. Identify the size chart in the input. Note the column headers
     (chest / bust / waist / hip / shoulder / sleeve / inseam …) and
     the units (cm or in).
  2. For every row, list the numeric ranges per column.
  3. Compare the user's measurements against the relevant columns.
  4. Pick the smallest size where every relevant user measurement
     fits inside (or equal to) the row's column upper bound.
  5. Apply the **bigger-on-tie** rule below.
  6. Emit the final JSON.

**Tie-breaking rule (very important):** when the user's measurements
fall *between* two sizes — i.e. they sit at the boundary of a smaller
size and the lower edge of the next one, OR they fit one critical
column tightly while the next size up gives clear room — ALWAYS
recommend the slightly **bigger** size. A garment that's a little
loose is wearable; one that's too tight is not. Mention the smaller
size as an alternative with ``"fit": "snug"`` so the user knows the
trade-off. Never recommend a size where one of the user's
measurements is larger than the column's upper bound by more than
1 cm (or 0.5 in).

Return ONLY valid JSON. No markdown, no backticks, no chain-of-thought.
Schema:

{
  "recommended_size":  "<single label from the chart, e.g. 'M' or 'EU 38'>",
  "confidence":        <float 0.0..1.0>,
  "garment_type":      "<your best inference, lowercase noun>",
  "size_chart_units":  "cm" | "in" | "mixed" | "unknown",
  "matched_columns":   ["chest", "waist", ...],
  "reasoning":         "<one short paragraph, 1-3 sentences, plain text. Briefly mention the bigger-on-tie reasoning when it applies.>",
  "alternatives":      [{"size":"S","fit":"snug"}, ...]
}

If you cannot find a usable chart in the input (e.g. the screenshot
shows only product photos and no table), set ``recommended_size`` to
null, ``confidence`` to 0.0, and explain in ``reasoning`` what was
missing so the user knows what to do next."""


def _build_user_prompt(
    *,
    chart_text: str,
    measurements: dict[str, Any],
    garment_type: str | None,
    store: str | None,
    page_title: str | None,
    user_preferred_units: str,
) -> str:
    meta_lines = []
    if store:
        meta_lines.append(f"STORE: {store}")
    if page_title:
        meta_lines.append(f"PAGE TITLE: {page_title}")
    if garment_type:
        meta_lines.append(f"GARMENT TYPE HINT: {garment_type}")
    meta_lines.append(f"USER PREFERS UNITS: {user_preferred_units}")
    meta = "\n".join(meta_lines)

    # Render measurements as a compact key:value list, dropping
    # missing keys so the model isn't tempted to invent values.
    cleaned: dict[str, Any] = {}
    for k, v in (measurements or {}).items():
        if v is None or v == "":
            continue
        cleaned[k] = v
    measurements_str = json.dumps(cleaned, ensure_ascii=False)

    chart_blob = chart_text.strip() if chart_text else "(image only — OCR the screenshot)"
    return (
        f"{meta}\n\n"
        f"USER MEASUREMENTS (JSON):\n{measurements_str}\n\n"
        f"SIZE CHART (raw):\n{chart_blob}\n"
    )


# ----------------------------- helpers -------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str, *, max_chars: int = 8000) -> str:
    """Cheap HTML -> text. Strips tags, collapses whitespace, trims.

    We deliberately avoid BeautifulSoup here to keep the dependency
    surface small; size charts are usually tiny tables that fit
    comfortably in the LLM context after this strip.

    To preserve the table's row structure for the heuristic regex
    fallback, we promote ``<tr>``, ``<br>``, ``</li>`` and a few other
    block-level closers to newlines before stripping the rest of the
    tags.
    """
    if not html:
        return ""
    # Inject newlines at row / line boundaries so the heuristic can
    # parse one size per line later.
    blob = re.sub(
        r"</?(?:tr|br\s*/?|li|p|div|h[1-6])\b[^>]*>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )
    # Cells inside a row become tab-separated so labels stay first.
    blob = re.sub(r"</?(?:td|th)\b[^>]*>", "\t", blob, flags=re.IGNORECASE)
    txt = _TAG_RE.sub(" ", blob)
    txt = _WS_RE.sub(" ", txt)
    lines = [ln.strip() for ln in txt.splitlines()]
    txt = "\n".join(ln for ln in lines if ln)
    if len(txt) > max_chars:
        txt = txt[:max_chars] + "\n…(truncated)"
    return txt


def _coerce_response(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction. LLMs sometimes wrap output in
    backticks despite the instruction; strip those defensively."""
    if not raw:
        return None
    s = raw.strip()
    # Strip ```json ... ``` fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # Find the first '{' .. last '}' window if extra prose surrounds it.
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
    """Coerce the LLM payload to ``AnalyzeChartOut`` regardless of
    minor type drift in the model's response."""
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
        source=source,
        elapsed_ms=elapsed_ms,
        has_measurements=has_measurements,
    )


# ----------------------------- LLM legs ------------------------------
async def _via_gemma(
    *, system_prompt: str, user_text: str, image_b64: str | None,
) -> str:
    """Hit the Eyes (Gemma-4) endpoint with the size-chart prompt.

    We send the screenshot if the caller provided one; the Space's
    Phase-2 mmproj will OCR it (Phase-1 silently sets vision_disabled
    and the model relies on the text we also pass)."""
    return await _call_gemma_space(
        system_prompt=system_prompt,
        user_text=user_text,
        image_b64_jpeg=image_b64 or "",
        max_tokens=600,
        temperature=0.1,
    )


# ----------------------- structured extraction -----------------------
_EXTRACTION_PROMPT = """You are an OCR-and-structure-extraction assistant.

Your single job: read the size chart in the input (HTML or screenshot)
and emit it as a strict JSON object. **Do not** recommend a size, do
**not** explain anything, do **not** add commentary or markdown — only
the JSON envelope below.

Schema (every field required):
{
  "headers": ["<column name>", ...],
  "units":   "cm" | "in" | "mixed" | "unknown",
  "rows": [
    {"label": "<size label e.g. 'S' or 'EU 38'>",
     "values": ["<cell text>", "<cell text>", ...]}
  ]
}

Rules:
* The first column is the size label; put it in ``label`` and EXCLUDE
  it from ``values``. ``values`` aligns 1-to-1 with ``headers`` AFTER
  dropping the size-label header (i.e. ``len(values) == len(headers)``).
* Keep cell text exactly as printed — preserve ranges like "86-90",
  decimals like "33.5", and unit suffixes if present in the cell.
* If the chart shows two unit systems (cm and in side-by-side),
  prefer the **cm** columns and set ``units`` to "cm".
* If the screenshot contains material other than the table (product
  photos, ads, buttons), ignore them and OCR the table only.
* If you cannot find a usable table, return {"headers":[],"units":"unknown","rows":[]}.

Output: JSON only, no prose."""


async def _extract_chart_structured(
    *, image_b64: str | None, chart_text: str,
) -> dict[str, Any] | None:
    """Pass-1: ask Gemma to OCR the chart into a strict JSON envelope.

    Returns ``{"headers": [...], "units": "cm", "rows": [...]}`` on
    success, or ``None`` if Gemma is unconfigured / errored / returned
    a non-conforming payload.
    """
    if not settings.EYES_GEMMA_SPACE_URL:
        return None
    if not image_b64 and not chart_text:
        return None
    user_text_parts: list[str] = []
    if chart_text:
        user_text_parts.append("Chart text (HTML stripped):\n" + chart_text)
    if image_b64:
        user_text_parts.append("Screenshot of the chart is attached as an image.")
    user_text = "\n\n".join(user_text_parts) or "Extract the size chart from the attached screenshot."
    try:
        raw = await _via_gemma(
            system_prompt=_EXTRACTION_PROMPT,
            user_text=user_text,
            image_b64=image_b64,
        )
    except Exception as exc:  # noqa: BLE001
        log.info("gemma extraction failed: %s", exc)
        return None
    parsed = _coerce_response(raw)
    if not isinstance(parsed, dict):
        return None
    rows = parsed.get("rows")
    headers = parsed.get("headers")
    if not isinstance(rows, list) or not rows:
        return None
    if not isinstance(headers, list):
        headers = []
    # Defensive: sanitise rows.
    cleaned_rows: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        label = r.get("label")
        values = r.get("values") or []
        if label is None or not isinstance(values, list):
            continue
        cleaned_rows.append({
            "label": str(label).strip()[:24],
            "values": [str(v).strip() for v in values],
        })
    if not cleaned_rows:
        return None
    return {
        "headers": [str(h).strip() for h in headers][:16],
        "units": str(parsed.get("units") or "unknown").lower()[:8],
        "rows": cleaned_rows,
    }


def _structured_to_text(struct: dict[str, Any]) -> str:
    """Turn a structured chart envelope into the tab-separated text
    representation that ``_heuristic_match`` parses cleanly.

    Format::

        Size  <header1>  <header2>  ...
        S     <value1>   <value2>   ...
        M     ...

    Tabs separate cells (so the heuristic's header-row detection
    splits on ``\\s{2,}|\\t|\\|`` reliably).
    """
    lines: list[str] = []
    headers = struct.get("headers") or []
    if headers:
        lines.append("\t".join(["Size"] + [str(h) for h in headers]))
    for r in struct.get("rows") or []:
        cells = [str(r.get("label", ""))] + [str(v) for v in (r.get("values") or [])]
        lines.append("\t".join(cells))
    return "\n".join(lines)


async def _via_qwen(
    *, system_prompt: str, user_text: str, image_b64: str | None = None,
) -> str:
    """Vision-aware fallback: DashScope Qwen-VL multimodal endpoint.

    Wrapped in ``asyncio.wait_for`` with an explicit cap so a sluggish
    DashScope round-trip doesn't keep the entire size endpoint hanging
    for the user-facing 30 s. If the call exceeds the budget we raise
    ``TimeoutError`` and let the orchestrator fall through to the
    heuristic, which now reads any HTML the extension forwards
    alongside the screenshot.
    """
    if not getattr(settings, "DASHSCOPE_API_KEY", None):
        raise RuntimeError("DASHSCOPE_API_KEY not configured for Qwen fallback.")
    try:
        from app.services.qwen_client import (
            QwenMessage, encode_image, get_qwen_client,
        )
    except ImportError as exc:
        raise RuntimeError("qwen_client unavailable.") from exc

    client = get_qwen_client()
    images: list[str] = []
    if image_b64:
        images.append(encode_image(image_b64))

    messages = [
        QwenMessage(role="system", text=system_prompt),
        QwenMessage(role="user", text=user_text, images=images),
    ]
    # 20 s budget: long enough for a one-shot multimodal call against a
    # warm DashScope instance, short enough that a stuck connection
    # doesn't strangle the size endpoint.
    return await asyncio.wait_for(
        client.chat(
            messages,
            model=settings.QWEN_BRAIN_MODEL,
            max_tokens=1500,
            temperature=0.1,
            response_format_json=True,
        ),
        timeout=20.0,
    )


# --------------------------- numeric fallback ------------------------
_RANGE_RE = re.compile(
    r"(?P<lo>\d{2,3}(?:[.,]\d)?)\s*[-–—~/]\s*(?P<hi>\d{2,3}(?:[.,]\d)?)",
)
# Single-number cell — used when a chart row holds exact garment
# dimensions (e.g. "S 68 100 50") rather than user-measurement ranges.
# We require at least 2 digits so we don't capture stray inches like
# "8" or label suffixes like "S2".
_SINGLE_NUM_RE = re.compile(r"\b(\d{2,3}(?:[.,]\d)?)\b")
_MEASUREMENT_FIELDS = ("chest", "bust", "waist", "hips", "hip", "shoulder", "shoulders", "inseam", "sleeve", "length", "bottom")


def _heuristic_match(*, chart_text: str,
                     measurements: dict[str, Any]) -> dict[str, Any] | None:
    """Last-resort: scan the chart text for size rows whose ranges fit
    the user's measurements.

    Algorithm (mirrors the LLM's tie-breaking rule):
      1. Parse the chart into rows of ``{label, ranges:[(lo, hi), …]}``.
      2. Collect the user's numeric chest / waist / hip values.
      3. Compute ``user_max`` = the largest of those values; this is the
         dimension that constrains size choice.
      4. Find the *smallest* row whose ``max(upper_bound)`` is ≥
         ``user_max`` — that row "accommodates" the user.
      5. **Bigger-on-tie:** if ``user_max`` is within 0.5 cm of that
         row's *tightest* upper bound (i.e. the user is brushing the
         ceiling on a critical dimension), bump the recommendation to
         the next row if one exists. This implements the user-requested
         rule: "if measurements fall between two sizes, recommend the
         slightly bigger one".
      6. Surface the smaller size as a ``snug`` alternative, mirroring
         the LLM contract.
    """
    if not chart_text or not measurements:
        return None

    # 1) Pull plausible numeric values (cm) from measurements.
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

    # 2) Parse rows from the chart text. Each row needs a label and
    #    at least one numeric range. We also capture the *header row*
    #    when one is present (the line that names the columns), so we
    #    can map user fields to chart columns by header keyword
    #    rather than by positional convention. This is what lets us
    #    handle "Size  Length  Bust  Shoulder" charts correctly.
    label_re = re.compile(r"^\s*([A-Za-z0-9./-]{1,8})\b")
    HEADER_TOKENS = {
        "size", "us", "uk", "eu", "cm", "in", "inches", "centimeters",
    }
    headers: list[str] | None = None  # column headers if we identified one
    rows: list[dict[str, Any]] = []
    for ln in chart_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # Header detection: a line that has no numeric ranges but
        # *does* contain at least two measurement-keyword tokens. The
        # column tokens are split on tabs / multiple spaces / pipes.
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
        # If no a-b ranges were found, treat each isolated number as a
        # point range (lo == hi). Common for stores that publish exact
        # garment dimensions (e.g. AliExpress "JACKET SIZE" tables).
        if not ranges:
            # Strip the leading size label so we don't capture "2" out of
            # "2XL" as a measurement.
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

    # 3) Pick the constraining user value (largest cm value).
    matched_field = max(user_vals, key=user_vals.get)

    # 3b) Map each user measurement to the chart's column index.
    #
    # Strategy A — header-based (when we found a header row):
    #   For each user field, find the header token whose text contains
    #   a synonym of that field. e.g. user "chest" matches header
    #   "Bust"; user "hip" matches "Bottom" via the bottom→hip alias.
    #
    # Strategy B — rank-based (fallback when no header row was found):
    #   Rank columns by minimum value; pair user fields by typical
    #   garment ordering (waist < chest/bust < hips).
    #
    # If the candidate column doesn't even contain the user's value,
    # we fall back to whichever column's union range does.
    ncols = max(len(r["ranges"]) for r in rows)
    columns: list[list[tuple[float, float]]] = [[] for _ in range(ncols)]
    for r in rows:
        for j, rng in enumerate(r["ranges"]):
            if j < ncols:
                columns[j].append(rng)

    # Synonym map: user-side measurement field -> chart-header keywords.
    _FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
        "chest":     ("chest", "bust"),
        "bust":      ("bust", "chest"),
        "waist":     ("waist"),
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
        """Find the chart column whose header best matches ``field``.

        Headers are aligned to ranges by *position*: the first header
        token after the size-label column corresponds to the first
        numeric range, etc. We therefore drop the leading "size"-ish
        header token, then return the offset of the matching token.
        """
        if not headers:
            return -1
        # Drop the first header token if it's the size-label column.
        body = list(headers)
        if body and (body[0] in HEADER_TOKENS or "size" in body[0]):
            body = body[1:]
        synonyms = _FIELD_SYNONYMS.get(field.lower(), (field.lower(),))
        for j, htext in enumerate(body):
            for syn in synonyms:
                if syn in htext:
                    return j
        return -1

    # Rank-based fallback.
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
        # Prefer header-based assignment when it agrees.
        idx = _header_index_for(field)
        if 0 <= idx < ncols:
            ranges = columns[idx]
            if ranges:
                col_max = max(hi for _, hi in ranges)
                # Generous tolerance: oversized garments (e.g. 100 cm
                # bust at S) intentionally don't contain the user's
                # 95 cm chest, so accept any column whose UPPER bound
                # is >= v even if the lower bound is above.
                if col_max >= v:
                    return idx
        # Rank-based fallback.
        rank = _FIELD_RANK.get(field.lower(), 1)
        if rank >= len(col_ranks):
            rank = len(col_ranks) - 1
        candidate = col_ranks[rank]
        ranges = columns[candidate]
        if ranges and max(hi for _, hi in ranges) >= v:
            return candidate
        # Final fallback: any column whose union upper bound >= v.
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
                continue  # column unmapped — skip this constraint
            _, hi = row["ranges"][j]
            if v > hi:
                return False
        return True

    def _row_is_tight(row: dict[str, Any]) -> bool:
        """A row is "tight" iff at least one user measurement sits
        within ``TIE_BUFFER_CM`` of the upper bound of a *real* range
        that contains it.

        Single-number cells (lo == hi) represent exact garment
        dimensions, not user-measurement brackets — bumping in that
        case would over-recommend on perfect fits, so we skip them.
        """
        for f, v in user_vals.items():
            j = field_to_col.get(f, -1)
            if j < 0 or j >= len(row["ranges"]):
                continue
            lo, hi = row["ranges"][j]
            if hi == lo:
                continue  # exact value, don't bump
            if lo <= v <= hi and (hi - v) < TIE_BUFFER_CM:
                return True
        return False

    # 4) Find smallest accommodating row.
    chosen_i: int | None = None
    for i, r in enumerate(rows):
        if _row_accommodates(r):
            chosen_i = i
            break

    bumped = False
    if chosen_i is None:
        # User exceeds every row — recommend the largest size we saw.
        chosen_i = len(rows) - 1
    elif _row_is_tight(rows[chosen_i]) and chosen_i + 1 < len(rows):
        # 5) Bigger-on-tie bump.
        chosen_i += 1
        bumped = True

    user_max = user_vals[matched_field]

    chosen = rows[chosen_i]
    smaller_alt = rows[chosen_i - 1] if chosen_i > 0 else None

    if bumped:
        reason = (
            f"Heuristic match: your {matched_field} ({user_max:g} cm) is right "
            f"at the upper edge of the smaller size, so DressApp recommends "
            f"the slightly bigger size {chosen['label'].upper()}. "
            f"AI sizing engines were unavailable; this is a regex-based "
            f"estimate."
        )
    else:
        reason = (
            f"Heuristic match: your {matched_field} ({user_max:g} cm) fits "
            f"the {chosen['label'].upper()} row. AI sizing engines were "
            f"unavailable; this is a regex-based estimate."
        )

    alternatives: list[dict[str, Any]] = []
    if bumped and smaller_alt is not None:
        alternatives.append({
            "size": smaller_alt["label"].upper(),
            "fit": "snug",
        })

    return {
        "recommended_size": chosen["label"].upper(),
        "confidence": 0.45,
        "garment_type": "unknown",
        "size_chart_units": "cm",
        "matched_columns": [matched_field],
        "reasoning": reason,
        "alternatives": alternatives,
    }


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
        # Don't fail — the LLM can still pick a "regular" size based on
        # garment defaults, and we surface ``has_measurements: false``
        # so the extension can prompt the user to fill in their
        # profile. Returning 422 here would be a worse UX.
        log.info(
            "size analyze called without measurements (user=%s)",
            (user or {}).get("id"),
        )

    # Materialise the chart text the LLM sees. Priority:
    #   1. parsed HTML  ->  2. caller-supplied plain text  ->  3. ""
    chart_text = ""
    if payload.chart_html:
        chart_text = _html_to_text(payload.chart_html)
    elif payload.chart_text:
        chart_text = payload.chart_text.strip()[:8000]

    if not chart_text and not payload.chart_screenshot_b64:
        raise HTTPException(
            status_code=422,
            detail="Provide chart_html, chart_text, or chart_screenshot_b64.",
        )

    user_prompt = _build_user_prompt(
        chart_text=chart_text,
        measurements=measurements,
        garment_type=payload.garment_type,
        store=payload.store,
        page_title=payload.page_title,
        user_preferred_units=payload.user_preferred_units,
    )

    active_provider = (await get_active_provider()).lower()  # for telemetry only
    parsed: dict[str, Any] | None = None
    source = "fallback"
    provider_errors: list[str] = []

    # Fast path: when the extension forwarded an HTML/text chart,
    # run the deterministic heuristic *before* touching any LLM.
    # This typically resolves in <50 ms and avoids the long tail of
    # Gemma / Qwen latency for the most common case (a real <table>
    # in a Size-Guide modal). LLMs only run when the heuristic
    # genuinely can't fit the user.
    if chart_text:
        decided = _heuristic_match(
            chart_text=chart_text, measurements=measurements,
        )
        if decided is not None:
            parsed = decided
            source = "heuristic"
            log.info(
                "size-chart resolved by heuristic-first in %d ms",
                int((time.time() - t0) * 1000),
            )

    # Step 0 — structured extraction via Gemma (image OCR, JSON-only).
    # When this succeeds, we feed the *cleaned* chart text into the
    # Python heuristic and skip the LLM "decision" call entirely:
    # Gemma does what it's good at (reading), Python does the math.
    # On failure we silently fall through to the legacy Gemma → Qwen
    # → heuristic stack so we never regress an existing working path.
    structured: dict[str, Any] | None = None
    if (
        parsed is None
        and (payload.chart_screenshot_b64 or payload.chart_html or payload.chart_text)
        and settings.EYES_GEMMA_SPACE_URL
    ):
        t_extract = time.time()
        try:
            structured = await _extract_chart_structured(
                image_b64=payload.chart_screenshot_b64,
                chart_text=chart_text,
            )
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"gemma-extract: {str(exc)[:200]}")
            structured = None
        provider_activity.record(
            "gemma", ok=structured is not None,
            latency_ms=int((time.time() - t_extract) * 1000),
            extra={"op": "size-chart/extract"},
        )
        if structured:
            extracted_text = _structured_to_text(structured)
            log.info(
                "gemma extracted %d rows / %d headers",
                len(structured.get("rows") or []),
                len(structured.get("headers") or []),
            )
            decided = _heuristic_match(
                chart_text=extracted_text, measurements=measurements,
            )
            if decided is not None:
                # Hand-craft a richer reasoning string for this path so
                # the user sees that Gemma actually read their chart
                # rather than the heuristic guessing on raw HTML.
                if decided.get("reasoning", "").startswith("Heuristic match:"):
                    decided["reasoning"] = decided["reasoning"].replace(
                        "AI sizing engines were unavailable; this is a regex-based estimate.",
                        "Chart extracted by Gemma-4 (Eyes); size chosen by DressApp's bigger-on-tie rule.",
                    )
                # Adopt the units Gemma reported when available.
                if structured.get("units") in {"cm", "in", "mixed", "unknown"}:
                    decided["size_chart_units"] = structured["units"]
                decided["confidence"] = max(decided.get("confidence", 0.0), 0.7)
                parsed = decided
                source = "gemma+heuristic"

    # Step 1 — Eyes (Gemma) decision call when extraction didn't yield.

    if parsed is None and settings.EYES_GEMMA_SPACE_URL:
        try:
            raw = await _via_gemma(
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_prompt,
                image_b64=payload.chart_screenshot_b64,
            )
            parsed = _coerce_response(raw)
            if parsed:
                source = "gemma"
            provider_activity.record(
                "gemma", ok=parsed is not None,
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart", "active_provider": active_provider},
            )
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"gemma: {str(exc)[:200]}")
            provider_activity.record(
                "gemma", ok=False,
                error=str(exc)[:240],
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart"},
            )

    # Step 2 — Qwen-VL fallback (multimodal: forwards screenshot to OCR).
    if parsed is None:
        try:
            raw = await _via_qwen(
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_prompt,
                image_b64=payload.chart_screenshot_b64,
            )
            parsed = _coerce_response(raw)
            if parsed:
                source = "qwen"
            provider_activity.record(
                "qwen", ok=parsed is not None,
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart", "with_image": bool(payload.chart_screenshot_b64)},
            )
        except Exception as exc:  # noqa: BLE001
            provider_errors.append(f"qwen: {str(exc)[:200]}")
            log.info("qwen fallback failed: %s; provider_errors=%s", exc, provider_errors)
            provider_activity.record(
                "qwen", ok=False,
                error=str(exc)[:240],
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart"},
            )

    # Step 3 — heuristic regex match.
    if parsed is None:
        parsed = _heuristic_match(
            chart_text=chart_text, measurements=measurements,
        )
        if parsed:
            source = "heuristic"

    if parsed is None:
        # Nothing worked. Surface why for easier debugging while keeping
        # the contract a 200 (so the extension can show a friendly
        # toast). The provider error list helps the user / support
        # know whether the LLM stack is misconfigured vs. genuinely
        # unable to read the chart.
        why_parts: list[str] = []
        if not provider_errors:
            why_parts.append(
                "AI sizing engines were not configured for this deployment."
            )
        else:
            why_parts.append(
                "AI sizing engines couldn't read this chart"
                + (
                    " (" + "; ".join(provider_errors) + ")"
                    if any("not configured" in e for e in provider_errors)
                    else ""
                )
                + "."
            )
        why_parts.append(
            "Try selecting the size table area manually with the pick "
            "tool, or open the page on a different device."
        )
        return AnalyzeChartOut(
            recommended_size=None,
            confidence=0.0,
            garment_type=payload.garment_type,
            size_chart_units=None,
            matched_columns=[],
            reasoning=" ".join(why_parts),
            alternatives=[],
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
