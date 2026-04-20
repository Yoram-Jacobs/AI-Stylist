"""The Eyes \u2014 Gemini multimodal garment analyzer.

Purpose
-------
Given a user-uploaded garment photo, return a structured ``GarmentAnalysis``
dict covering every field of the Add-Item form (name, caption, category,
sub-category, item type, brand, fabric composition, colours, pattern,
gender, dress code, season, tradition, state, condition, quality, size,
price, tags, and \u2014 if the condition is poor \u2014 a short repair_advice).

Implementation
--------------
* Calls **Gemini 2.5 Pro** via the Emergent universal key (swappable later
  to Gemma 4 E4B once the user's fine-tune is ready \u2014 only the
  ``model`` attribute needs to change).
* Uses a strict JSON contract prompt; we then parse with the same resilient
  extractor used by the stylist and trend-scout.
* Reports latency + success to the provider-activity ring buffer so the
  Admin dashboard shows its health alongside every other provider.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
import uuid
from typing import Any

from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
from PIL import Image

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are The Eyes \u2014 DressApp's visual garment analyst. You look at a "
    "single clothing photo and describe it in exhaustive, merchandisable "
    "detail. Your output is used to auto-fill an Add-Item form that a user "
    "will review, so be confident but never invent sensitive claims (e.g. "
    "do not guess a specific brand unless clearly visible; leave brand "
    "blank otherwise).\n\n"
    "Return ONLY a JSON object with the following shape (all keys optional "
    "except `title`):\n"
    "{\n"
    '  "name": string,                     // short friendly descriptor, 2\u20135 words, e.g. "Cream Linen Blazer"\n'
    '  "title": string,                    // fallback short title (required)\n'
    '  "caption": string,                  // friendly natural one-paragraph description (<= 240 chars). If state is Bad, include kind, actionable repair/enhancement advice.\n'
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
    "Voice guidance for `name` and `caption`: friendly, professional, "
    "natural \u2014 write like a thoughtful editor, never salesy, never "
    "robotic. No emojis, no markdown, no hashtags."
)


def _extract_json(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:  # noqa: BLE001
            pass
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(raw[first : last + 1])
        except Exception:  # noqa: BLE001
            pass
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


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


class GarmentVisionService:
    def __init__(self) -> None:
        if not settings.EMERGENT_LLM_KEY:
            raise RuntimeError(
                "EMERGENT_LLM_KEY is not configured; The Eyes analyzer unavailable."
            )
        self.api_key = settings.EMERGENT_LLM_KEY
        # Start with Gemini 2.5 Pro; swap to fine-tuned Gemma later via env.
        self.model = settings.GARMENT_VISION_MODEL
        self.provider = settings.GARMENT_VISION_PROVIDER

    async def analyze(self, image_bytes: bytes) -> dict[str, Any]:
        shrunk = _shrink_for_vision(image_bytes)
        b64 = base64.b64encode(shrunk).decode("ascii")
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"theeyes-{uuid.uuid4().hex[:12]}",
            system_message=SYSTEM_PROMPT,
        )
        chat.with_model(self.provider, self.model)
        msg = UserMessage(
            text=(
                "Analyze this garment photograph. Return the JSON object only."
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
                "garment-vision",
                ok=ok,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=last_err,
                extra={"model": self.model},
            )
        parsed = _extract_json(raw or "")
        if not parsed.get("title") and parsed.get("name"):
            parsed["title"] = parsed["name"]
        if not parsed.get("title"):
            parsed["title"] = "Unnamed garment"
        parsed["model_used"] = self.model
        parsed["raw"] = {"preview": (raw or "")[:500]}
        logger.info(
            "The Eyes OK model=%s category=%s sub=%s item_type=%s condition=%s",
            self.model,
            parsed.get("category"),
            parsed.get("sub_category"),
            parsed.get("item_type"),
            parsed.get("condition"),
        )
        return parsed


garment_vision_service = (
    GarmentVisionService() if settings.EMERGENT_LLM_KEY else None
)
