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
  * A clothing size chart from a third-party shopping site (HTML, plain
    text, or as an image to OCR).
  * The user's body measurements.
  * Optional metadata: garment type hint, store name, page title.

Pick the size that best fits the user. Honour each measurement column
strictly — never recommend a size where one of the user's measurements
is larger than the column's upper bound by more than 1 cm (or 0.5 in).
When two sizes are valid, prefer the smaller one for slim garments
(shirt, dress, blouse, pants) and the larger one for outerwear (coat,
jacket, hoodie). When measurements straddle two sizes, name the chosen
size and mention the alternative in ``alternatives``.

Return ONLY valid JSON. No markdown, no backticks. Schema:

{
  "recommended_size":  "<single label from the chart, e.g. 'M' or 'EU 38'>",
  "confidence":        <float 0.0..1.0>,
  "garment_type":      "<your best inference, lowercase noun>",
  "size_chart_units":  "cm" | "in" | "mixed" | "unknown",
  "matched_columns":   ["chest", "waist", ...],
  "reasoning":         "<one short paragraph, 1-3 sentences, plain text>",
  "alternatives":      [{"size":"L","fit":"looser"}, ...]
}

If you can't find a usable chart in the input, set
``recommended_size`` to null, ``confidence`` to 0.0, and explain in
``reasoning``."""


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


async def _via_qwen(*, system_prompt: str, user_text: str) -> str:
    """Fallback: DashScope Qwen text endpoint.

    We deliberately use the text-only path here (not Qwen-VL) because:
      a) the chart text we already extracted is cheaper + faster,
      b) the user's screenshot path goes to Gemma-4 anyway in step 1.
    Lazy-import dashscope so a deploy without the Qwen key doesn't
    fail to load this module.
    """
    if not getattr(settings, "DASHSCOPE_API_KEY", None):
        raise RuntimeError("DASHSCOPE_API_KEY not configured for Qwen fallback.")
    try:
        import dashscope  # type: ignore
    except ImportError as exc:
        raise RuntimeError("dashscope SDK not installed.") from exc

    dashscope.api_key = settings.DASHSCOPE_API_KEY
    resp = dashscope.Generation.call(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        result_format="message",
        temperature=0.1,
        max_tokens=600,
    )
    if getattr(resp, "status_code", 200) != 200:
        raise RuntimeError(f"Qwen status {resp.status_code}: {getattr(resp, 'message', '')[:200]}")
    out = resp.output  # type: ignore[attr-defined]
    try:
        return out["choices"][0]["message"]["content"]  # type: ignore[index]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Qwen unexpected response shape: {exc}") from exc


# --------------------------- numeric fallback ------------------------
_RANGE_RE = re.compile(
    r"(?P<lo>\d{2,3}(?:[.,]\d)?)\s*[-–—~/]\s*(?P<hi>\d{2,3}(?:[.,]\d)?)",
)
_MEASUREMENT_FIELDS = ("chest", "bust", "waist", "hips", "hip")


def _heuristic_match(*, chart_text: str,
                     measurements: dict[str, Any]) -> dict[str, Any] | None:
    """Last-resort: scan the chart text for ranges that bracket the
    user's chest/waist/hip measurements. Picks the *first* size label
    whose ranges contain at least one user measurement."""
    if not chart_text or not measurements:
        return None
    # Pull plausible numeric values (cm) from measurements.
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
    # Slice chart into rows by line; for each row find ranges and a
    # "size label" as the first non-numeric-looking token.
    lines = [ln for ln in chart_text.splitlines() if ln.strip()]
    label_re = re.compile(r"^\s*([A-Za-z0-9./-]{1,8})\b")
    for ln in lines:
        m = label_re.match(ln)
        if not m:
            continue
        label = m.group(1)
        # Skip header rows.
        if label.lower() in {"size", "us", "uk", "eu", "cm", "in"}:
            continue
        ranges = _RANGE_RE.findall(ln)
        if not ranges:
            continue
        for col_idx, (lo, hi) in enumerate(ranges):
            try:
                lo_f = float(lo.replace(",", "."))
                hi_f = float(hi.replace(",", "."))
            except ValueError:
                continue
            for field, val in user_vals.items():
                if lo_f <= val <= hi_f:
                    return {
                        "recommended_size": label.upper(),
                        "confidence": 0.4,
                        "garment_type": "unknown",
                        "size_chart_units": "cm",
                        "matched_columns": [field],
                        "reasoning": (
                            f"Heuristic match: {field} {val:g} cm fits the "
                            f"{label.upper()} row ({lo_f:g}–{hi_f:g} cm). "
                            f"AI sizing engines were unavailable; this is "
                            f"a regex-based estimate."
                        ),
                        "alternatives": [],
                    }
    return None


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

    # Step 1 — Eyes (Gemma) when active and wired.
    active_provider = (await get_active_provider()).lower()
    parsed: dict[str, Any] | None = None
    source = "fallback"
    err_first: str | None = None

    if (
        active_provider == "gemma"
        and settings.EYES_GEMMA_SPACE_URL
    ):
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
                extra={"op": "size-chart"},
            )
        except Exception as exc:  # noqa: BLE001
            err_first = f"gemma: {exc}"
            provider_activity.record(
                "gemma", ok=False,
                error=str(exc)[:240],
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart"},
            )

    # Step 2 — Qwen fallback (text only).
    if parsed is None:
        try:
            raw = await _via_qwen(
                system_prompt=_SYSTEM_PROMPT, user_text=user_prompt,
            )
            parsed = _coerce_response(raw)
            if parsed:
                source = "qwen"
            provider_activity.record(
                "qwen", ok=parsed is not None,
                latency_ms=int((time.time() - t0) * 1000),
                extra={"op": "size-chart"},
            )
        except Exception as exc:  # noqa: BLE001
            log.info("qwen fallback failed: %s; first=%s", exc, err_first)
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
        # Nothing worked. Return a 200 with a graceful "couldn't tell"
        # so the extension can show the user a friendly message
        # instead of a Sentry-grade error toast.
        return AnalyzeChartOut(
            recommended_size=None,
            confidence=0.0,
            garment_type=payload.garment_type,
            size_chart_units=None,
            matched_columns=[],
            reasoning=(
                "We couldn't determine a size from this chart. "
                "Try selecting the size table area manually, or open "
                "the page on a different device and try again."
            ),
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
