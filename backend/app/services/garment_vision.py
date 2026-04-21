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

import asyncio
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


def _coerce_enums(parsed: dict[str, Any]) -> dict[str, Any]:
    """Best-effort coercion of AI-returned enum values.

    * Unknown / empty values are dropped rather than kept, so Pydantic's
      optional-enum fields stay valid (None instead of an unknown literal).
    * ``state`` is the main hazard: the model sometimes echoes the
      ``condition`` value there. We infer ``used`` by default, but flip
      to ``new`` if the item is also labelled ``excellent`` and looks
      brand-new.
    """
    # gender
    g = _norm_str(parsed.get("gender"))
    if g and g not in _VALID_GENDER:
        g = {"male": "men", "female": "women", "uni": "unisex", "kid": "kids"}.get(g)
    parsed["gender"] = g if g in _VALID_GENDER else None

    # dress_code
    dc = _norm_str(parsed.get("dress_code"))
    if dc:
        dc = dc.replace(" ", "-")
        if dc == "athleisure":
            dc = "athletic"
        if dc == "lounge":
            dc = "loungewear"
    parsed["dress_code"] = dc if dc in _VALID_DRESS_CODE else None

    # condition
    c = _norm_str(parsed.get("condition"))
    if c == "poor":
        c = "bad"
    if c == "very-good":
        c = "excellent"
    parsed["condition"] = c if c in _VALID_CONDITION else None

    # state \u2014 coerce unknowns based on other signals
    s = _norm_str(parsed.get("state"))
    if s not in _VALID_STATE:
        s = "used"  # sensible default; user can flip to "new" in the form
    parsed["state"] = s

    # quality
    q = _norm_str(parsed.get("quality"))
    q_map = {
        "cheap": "budget", "entry": "budget", "basic": "budget",
        "mid-range": "mid", "standard": "mid",
        "high": "premium", "high-end": "premium",
    }
    q = q_map.get(q, q)
    parsed["quality"] = q if q in _VALID_QUALITY else None

    # pattern
    p = _norm_str(parsed.get("pattern"))
    parsed["pattern"] = p if p in _VALID_PATTERN else None

    # season \u2014 must be a list of known tokens
    allowed_seasons = {"spring", "summer", "fall", "autumn", "winter", "all"}
    raw_seasons = parsed.get("season") or []
    if isinstance(raw_seasons, str):
        raw_seasons = [raw_seasons]
    seasons: list[str] = []
    for s2 in raw_seasons:
        tok = _norm_str(s2)
        if tok == "autumn":
            tok = "fall"
        if tok in allowed_seasons:
            seasons.append(tok)
    parsed["season"] = seasons

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
        if not settings.EMERGENT_LLM_KEY:
            raise RuntimeError(
                "EMERGENT_LLM_KEY is not configured; The Eyes analyzer unavailable."
            )
        self.api_key = settings.EMERGENT_LLM_KEY
        # Start with Gemini 2.5 Pro; swap to fine-tuned Gemma later via env.
        self.model = settings.GARMENT_VISION_MODEL
        self.provider = settings.GARMENT_VISION_PROVIDER
        # Detection only needs fast bounding boxes \u2014 use Flash so the
        # multi-item pipeline stays under the ingress timeout budget.
        self.detect_model = "gemini-2.5-flash"
        # Faster per-crop analyser (still Gemini) \u2014 configurable.
        self.crop_model = settings.GARMENT_VISION_CROP_MODEL
        self.max_items = settings.GARMENT_VISION_MAX_ITEMS

    # -------------------- public API --------------------
    async def detect_items(self, image_bytes: bytes) -> list[dict[str, Any]]:
        """Return a list of ``{label, kind, bbox}`` entries."""
        shrunk = _shrink_for_vision(image_bytes, max_side=1024, q=80)
        b64 = base64.b64encode(shrunk).decode("ascii")
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"theeyes-detect-{uuid.uuid4().hex[:12]}",
            system_message=DETECT_SYSTEM_PROMPT,
        )
        chat.with_model(self.provider, self.detect_model)
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
        items = parsed.get("items") or []
        if not isinstance(items, list):
            items = []
        # Minimal validation + normalisation first.
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
        self, image_bytes: bytes, *, model: str | None = None
    ) -> dict[str, Any]:
        shrunk = _shrink_for_vision(image_bytes)
        b64 = base64.b64encode(shrunk).decode("ascii")
        use_model = model or self.model
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"theeyes-{uuid.uuid4().hex[:12]}",
            system_message=SYSTEM_PROMPT,
        )
        chat.with_model(self.provider, use_model)
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
                extra={"model": use_model},
            )
        parsed = _extract_json(raw or "")
        if not parsed.get("title") and parsed.get("name"):
            parsed["title"] = parsed["name"]
        if not parsed.get("title"):
            parsed["title"] = "Unnamed garment"
        # Sanitise AI-returned enum-like values so downstream Pydantic
        # validation never 422s on a Flash slip.
        parsed = _coerce_enums(parsed)
        parsed["model_used"] = use_model
        parsed["raw"] = {"preview": (raw or "")[:500]}
        logger.info(
            "The Eyes OK model=%s category=%s sub=%s item_type=%s condition=%s",
            use_model,
            parsed.get("category"),
            parsed.get("sub_category"),
            parsed.get("item_type"),
            parsed.get("condition"),
        )
        return parsed

    # -------------------- multi-item outfit pipeline --------------------
    async def analyze_outfit(
        self, image_bytes: bytes, *, max_items: int | None = None
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
        # 1) Detect every visible item. Soft-fail to whole-frame analysis
        #    if the detector errors or is unavailable.
        try:
            detections = await self.detect_items(image_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "detect_items failed (%s); falling back to single analysis",
                repr(exc)[:160],
            )
            detections = []

        # Soft-normalise: if the detector saw one giant box that covers
        # the frame, treat it as a single-item analysis (no point paying
        # for an extra LLM call on the identical image).
        useful: list[dict[str, Any]] = []
        for det in detections:
            bbox = det.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            ymin, xmin, ymax, xmax = bbox
            area = max(0, (ymax - ymin)) * max(0, (xmax - xmin))
            if area >= 1000 * 1000 * 0.9:
                # near-full-frame box; skip, the analyze call will cover it
                continue
            useful.append(det)
        # Cap work to avoid runaway cost / latency on very busy photos.
        cap = max_items if max_items is not None else self.max_items
        useful = useful[:cap]

        if not useful:
            single = await self.analyze(image_bytes)
            crop_b64 = base64.b64encode(image_bytes).decode("ascii")
            return [
                {
                    "label": single.get("item_type") or single.get("sub_category") or "garment",
                    "kind": "garment",
                    "bbox": [0, 0, 1000, 1000],
                    "crop_base64": crop_b64,
                    "crop_mime": "image/jpeg",
                    "analysis": single,
                }
            ]

        # 2) Crop each bbox on a thread-pool (Pillow work is CPU-bound).
        crops: list[tuple[dict[str, Any], bytes]] = []

        def _crop_all() -> list[tuple[dict[str, Any], bytes]]:
            out: list[tuple[dict[str, Any], bytes]] = []
            for det in useful:
                cropped = _crop_to_bbox(image_bytes, det["bbox"])
                if not cropped:
                    continue
                crop_bytes, _xy = cropped
                out.append((det, crop_bytes))
            return out

        crops = await asyncio.to_thread(_crop_all)
        if not crops:
            # Every crop was rejected (tiny / invalid bbox). Degrade gracefully.
            single = await self.analyze(image_bytes)
            crop_b64 = base64.b64encode(image_bytes).decode("ascii")
            return [
                {
                    "label": single.get("item_type") or single.get("sub_category") or "garment",
                    "kind": "garment",
                    "bbox": [0, 0, 1000, 1000],
                    "crop_base64": crop_b64,
                    "crop_mime": "image/jpeg",
                    "analysis": single,
                }
            ]

        # 3) Parallel analysis with bounded concurrency. We use Flash
        #    for per-crop calls to stay inside the ingress timeout budget;
        #    crops are small and structurally simple, so Flash quality is
        #    ample. Pro remains the default for single-image analysis.
        sem = asyncio.Semaphore(6)

        async def _one(det: dict[str, Any], crop_bytes: bytes) -> dict[str, Any] | None:
            async with sem:
                try:
                    analysis = await self.analyze(crop_bytes, model=self.crop_model)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "crop analyze failed for label=%s: %s",
                        det.get("label"),
                        repr(exc)[:160],
                    )
                    return None
                return {
                    "label": det.get("label") or "garment",
                    "kind": det.get("kind") or "garment",
                    "bbox": det.get("bbox"),
                    "crop_base64": base64.b64encode(crop_bytes).decode("ascii"),
                    "crop_mime": "image/jpeg",
                    "analysis": analysis,
                }

        results = await asyncio.gather(*[_one(d, b) for d, b in crops])
        items = [r for r in results if r]
        # If every parallel call failed, fall back once.
        if not items:
            single = await self.analyze(image_bytes)
            crop_b64 = base64.b64encode(image_bytes).decode("ascii")
            return [
                {
                    "label": single.get("item_type") or "garment",
                    "kind": "garment",
                    "bbox": [0, 0, 1000, 1000],
                    "crop_base64": crop_b64,
                    "crop_mime": "image/jpeg",
                    "analysis": single,
                }
            ]
        logger.info(
            "analyze_outfit OK detected=%d analysed=%d labels=%s",
            len(useful),
            len(items),
            [i["label"] for i in items][:8],
        )
        return items


garment_vision_service = (
    GarmentVisionService() if settings.EMERGENT_LLM_KEY else None
)
