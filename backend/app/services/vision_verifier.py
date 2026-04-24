"""Vision verifier — Gemini audit that checks the parser output (Fix 3).

Runs AFTER the clothing parser returns N garment candidates. Asks Gemini
(multimodal) to look at the original photo and answer:
  - how many distinct garments are actually present?
  - for each of our candidate crops, does it contain exactly one garment
    (not zero, not merged multiples)?

If the audit disagrees materially with the parser output (e.g. parser
returned 1 item but audit sees 2), we flag it for the caller which then
decides whether to re-run segmentation or hand over to the user.

The verifier is deliberately cheap — one Gemini Flash call, two images
max (original + montage of crops). Never fatal; returns a permissive
default on any error.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from typing import Any

from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

_AUDIT_PROMPT = (
    "You are a clothing cataloguer. The FIRST image is the original photo. "
    "The SECOND image is a montage of numbered crops extracted by an "
    "automatic parser. Reply with ONLY strict JSON.\n\n"
    "Schema:\n"
    "{\n"
    '  "garments_in_original": int,   // distinct wearable items you see\n'
    '  "crops": [\n'
    "    {\n"
    '      "index": int,               // 1-based\n'
    '      "looks_single_garment": boolean,\n'
    '      "issues": string[]          // e.g. ["merged with pants", "background noise", "cut off"]\n'
    "    }\n"
    "  ],\n"
    '  "verdict": "ok" | "needs_resegment" | "needs_review"\n'
    "}\n\n"
    'Set verdict="needs_resegment" if the parser under-split (fewer crops'
    ' than garments). "needs_review" if crops are noisy/partial. "ok" otherwise.'
)


def _make_montage(crops: list[bytes], *, cell: int = 280) -> bytes | None:
    if not crops:
        return None
    images = []
    for b in crops:
        try:
            im = Image.open(io.BytesIO(b)).convert("RGB")
            im.thumbnail((cell, cell))
            images.append(im)
        except Exception:  # noqa: BLE001
            continue
    if not images:
        return None
    cols = min(3, len(images))
    rows = (len(images) + cols - 1) // cols
    W, H = cols * cell, rows * cell
    canvas = Image.new("RGB", (W, H), (245, 245, 245))
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = c * cell + (cell - im.size[0]) // 2
        y = r * cell + (cell - im.size[1]) // 2
        canvas.paste(im, (x, y))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _extract_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


async def audit(
    original_image: bytes,
    candidate_crops: list[bytes],
) -> dict[str, Any]:
    """Returns {garments_in_original, crops:[...], verdict} or permissive default."""
    default = {
        "garments_in_original": len(candidate_crops),
        "crops": [
            {"index": i + 1, "looks_single_garment": True, "issues": []}
            for i, _ in enumerate(candidate_crops)
        ],
        "verdict": "ok",
        "skipped": False,
    }
    if not candidate_crops:
        return {**default, "skipped": True}
    montage = _make_montage(candidate_crops)
    if montage is None:
        return {**default, "skipped": True}
    api_key = settings.EMERGENT_LLM_KEY
    if not api_key:
        logger.info("vision_verifier: EMERGENT_LLM_KEY missing, skipping")
        return {**default, "skipped": True}
    try:
        from emergentintegrations.llm.chat import (
            ImageContent,
            LlmChat,
            UserMessage,
        )

        chat = LlmChat(
            api_key=api_key,
            session_id=f"verifier-{uuid.uuid4().hex[:10]}",
            system_message=(
                "You are a precise clothing parser auditor. "
                "Respond with strict JSON only — no prose, no code fences."
            ),
        )
        chat.with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(
            text=_AUDIT_PROMPT,
            file_contents=[
                ImageContent(image_base64=_b64(original_image)),
                ImageContent(image_base64=_b64(montage)),
            ],
        )
        raw = await chat.send_message(msg)
        parsed = _extract_json(raw or "") or default
        verdict = parsed.get("verdict") or "ok"
        out = {
            "garments_in_original": int(
                parsed.get("garments_in_original") or len(candidate_crops)
            ),
            "crops": parsed.get("crops") or default["crops"],
            "verdict": verdict,
            "skipped": False,
        }
        logger.info(
            "vision_verifier: verdict=%s garments=%s (had %d crops)",
            verdict,
            out["garments_in_original"],
            len(candidate_crops),
        )
        return out
    except Exception as exc:  # noqa: BLE001
        logger.info("vision_verifier failed (non-fatal): %s", exc)
        return {**default, "skipped": True, "error": str(exc)[:120]}
