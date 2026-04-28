"""Outfit Composer (Phase R) — the brain behind the Stylist Power-Up.

Pipeline (per ``compose_outfit`` call):

    1. Analyse each uploaded image in parallel with the existing
       ``garment_vision`` pipeline → list of ``CandidateGarment``.
    2. Deduplicate near-twins (same shirt photographed three ways, or two
       very similar T-shirts) using cheap signature hashing then a
       perceptual fallback. Keeps the highest-quality survivor per group.
    3. Score each survivor against the user's brief: occasion,
       formality, palette match, season/weather, modesty notes.
    4. Compose: assign survivors to head-to-toe slots
       (top/bottom/dress/outerwear/shoes/accessory), filling from the
       user's closet for any remaining gaps.
    5. Detect *true* gaps (no candidate, no closet match) and call
       ``marketplace_search`` to suggest 1-3 listings per gap.
    6. Run the heuristic ``professional_matcher`` over the brief +
       results to optionally surface a single pro card.
    7. Build & return the structured ``OutfitCanvas``.

The composer is **model-agnostic** — every LLM call goes through
``app.services.gemini_stylist`` /​ ``garment_vision`` which already obey
``settings.gemini_chat_key``. When the Gemma 4 fine-tune lands those two
modules are the only files that need to change.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from typing import Any

from app.config import settings
from app.db.database import get_db
from app.services import (
    marketplace_search,
    professional_matcher,
    repos,
)
from app.services.garment_vision import garment_vision_service
from app.services.gemini_stylist import gemini_stylist_service
from app.services.thumbnails import make_thumb_from_data_url

logger = logging.getLogger(__name__)


# ─── tunables ────────────────────────────────────────────────
MAX_CANDIDATES = 8           # hard cap to keep latency + token cost bounded
DEDUP_HASH_PREFIX_BITS = 64  # block-hash precision for cheap dedup
SLOT_PRIORITY: list[str] = [
    "top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag", "headwear"
]


# ─── public entry point ─────────────────────────────────────
async def compose_outfit(
    *,
    user: dict[str, Any],
    brief: str,
    image_bytes_list: list[bytes],
    language: str = "en",
    constraints: dict[str, Any] | None = None,
    user_preferences_block: str | None = None,
) -> dict[str, Any]:
    """Run the full composer pipeline and return a serialised
    ``OutfitCanvas`` dict ready to ship to the frontend / persist.
    """
    constraints = constraints or {}
    t0 = time.perf_counter()
    canvas_id = str(uuid.uuid4())
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    timings: dict[str, int] = {}

    # 1) Per-image analysis ----------------------------------------
    if image_bytes_list:
        candidates = await _analyze_uploads(image_bytes_list[:MAX_CANDIDATES])
    timings["analyze_ms"] = int((time.perf_counter() - t0) * 1000)

    # 2) Dedup -----------------------------------------------------
    t1 = time.perf_counter()
    candidates, dedup_rejects = _dedup_candidates(candidates)
    rejected.extend(dedup_rejects)
    timings["dedup_ms"] = int((time.perf_counter() - t1) * 1000)

    # 3) Brief scoring + outfit composition ------------------------
    t2 = time.perf_counter()
    composition = await _compose_with_llm(
        brief=brief,
        candidates=candidates,
        constraints=constraints,
        language=language,
        user_preferences_block=user_preferences_block,
    )
    timings["compose_ms"] = int((time.perf_counter() - t2) * 1000)

    # Merge LLM-rejected with previous rejects.
    rejected.extend(composition.get("rejected", []))
    slots: list[dict[str, Any]] = composition.get("slots", [])
    summary: str = composition.get("summary") or _fallback_summary(brief, slots, language)
    detailed: str | None = composition.get("detailed_rationale")

    # Update brief_match_score / quality_score on candidates from LLM signal.
    score_map = composition.get("scores", {}) or {}
    for c in candidates:
        if c["candidate_id"] in score_map:
            c["brief_match_score"] = float(score_map[c["candidate_id"]])

    # 4) Closet fallback for empty slots ---------------------------
    t3 = time.perf_counter()
    if any(s.get("is_gap") for s in slots):
        await _fill_gaps_from_closet(
            user_id=user.get("id"),
            slots=slots,
            candidates=candidates,
            brief=brief,
        )
    timings["closet_fill_ms"] = int((time.perf_counter() - t3) * 1000)

    # 5) Marketplace fill for still-empty slots --------------------
    t4 = time.perf_counter()
    market_suggestions: list[dict[str, Any]] = []
    open_gaps = [s for s in slots if s.get("is_gap")]
    if open_gaps:
        market_suggestions = await marketplace_search.suggest_for_gaps(
            user=user,
            gaps=open_gaps,
            brief=brief,
            constraints=constraints,
        )
    timings["marketplace_ms"] = int((time.perf_counter() - t4) * 1000)

    # 6) Professional referral (heuristic) -------------------------
    t5 = time.perf_counter()
    pro_suggestion = await professional_matcher.maybe_suggest(
        brief=brief,
        constraints=constraints,
        slots=slots,
        candidates=candidates,
        user=user,
    )
    timings["pro_ms"] = int((time.perf_counter() - t5) * 1000)

    timings["total_ms"] = int((time.perf_counter() - t0) * 1000)

    return {
        "canvas_id": canvas_id,
        "schema_version": 1,
        "brief": brief,
        "language": language,
        "summary": summary,
        "detailed_rationale": detailed,
        "slots": slots,
        "candidates": candidates,
        "rejected": rejected,
        "marketplace_suggestions": market_suggestions,
        "professional_suggestion": pro_suggestion,
        "model_used": composition.get("model_used"),
        "latency_ms": timings,
    }


# ─── 1) per-image analysis ──────────────────────────────────
async def _analyze_uploads(image_bytes_list: list[bytes]) -> list[dict[str, Any]]:
    """Run garment_vision on every upload concurrently."""
    if garment_vision_service is None:
        logger.warning("garment_vision_service is None — composer running blind")
        return []
    sem = asyncio.Semaphore(3)  # bounded so we don't blow Atlas / model RAM

    async def _one(idx: int, raw: bytes) -> dict[str, Any] | None:
        async with sem:
            try:
                analysis = await garment_vision_service.analyze(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Composer analyze[%d] failed: %s", idx, repr(exc)[:160])
                return None
        thumb = _data_url_for(raw)
        cid = str(uuid.uuid4())
        title = analysis.get("title") or "Garment"
        category = (analysis.get("category") or "").lower() or None
        return {
            "candidate_id": cid,
            "source": "upload",
            "image_data_url": thumb,
            "closet_item_id": None,
            "title": title,
            "category": category,
            "sub_category": analysis.get("sub_category"),
            "color": analysis.get("color"),
            "pattern": analysis.get("pattern"),
            "material": analysis.get("material"),
            "brand": analysis.get("brand"),
            "formality": analysis.get("formality"),
            "season": analysis.get("season"),
            "tags": analysis.get("tags") or [],
            "quality_score": float(analysis.get("confidence", 0.7) or 0.7),
            "brief_match_score": 0.0,
            "dedup_group_id": None,
            # Internal-only signature for cheap dedup; not part of the
            # public schema, popped before serialisation.
            "_signature": _signature_for(category, analysis.get("color"), analysis.get("pattern")),
        }

    results = await asyncio.gather(
        *[_one(i, raw) for i, raw in enumerate(image_bytes_list)],
        return_exceptions=False,
    )
    return [r for r in results if r]


def _data_url_for(raw: bytes) -> str | None:
    """Generate a small JPEG data URL for the candidate preview."""
    import base64
    try:
        # Already a data URL? unlikely here but harmless.
        b64 = base64.b64encode(raw).decode("ascii")
        full = f"data:image/jpeg;base64,{b64}"
        return make_thumb_from_data_url(full)
    except Exception as exc:  # noqa: BLE001
        logger.info("Composer thumb build failed: %s", repr(exc)[:160])
        return None


def _signature_for(category: str | None, color: str | None, pattern: str | None) -> str:
    """Cheap hash for first-pass dedup. Same category+color+pattern bucket
    means the LLM will sort out the survivor in step 2.
    """
    payload = f"{category or '?'}|{(color or '?').lower()}|{(pattern or '?').lower()}"
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


# ─── 2) dedup ───────────────────────────────────────────────
def _dedup_candidates(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Group candidates by signature; keep the highest quality survivor.

    Anything dropped goes into the ``rejected`` list with reason='duplicate'
    and a ``kept_candidate_id`` pointer so the UI can draw the visual line.
    """
    by_sig: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_sig.setdefault(c["_signature"], []).append(c)

    survivors: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for sig, group in by_sig.items():
        # Sort by quality score desc; first one wins.
        group.sort(key=lambda x: x.get("quality_score", 0.0), reverse=True)
        winner = group[0]
        survivors.append(winner)
        if len(group) > 1:
            for loser in group[1:]:
                loser["dedup_group_id"] = sig
                rejects.append(
                    {
                        "candidate_id": loser["candidate_id"],
                        "reason": "duplicate",
                        "detail": f"Looks like a near-duplicate of {winner.get('title') or 'another upload'}.",
                        "kept_candidate_id": winner["candidate_id"],
                    }
                )
            winner["dedup_group_id"] = sig
    return survivors, rejects


# ─── 3) LLM composition ────────────────────────────────────
async def _compose_with_llm(
    *,
    brief: str,
    candidates: list[dict[str, Any]],
    constraints: dict[str, Any],
    language: str,
    user_preferences_block: str | None = None,
) -> dict[str, Any]:
    """Ask the Stylist LLM to assign candidates to outfit slots.

    Returns a dict with ``slots`` (list[OutfitSlot dict]), ``rejected``
    (list[RejectedCandidate dict]), ``summary``, ``detailed_rationale``,
    ``scores`` (candidate_id -> 0..1), and ``model_used``.
    """
    if not candidates:
        # Nothing to compose — still return an empty canvas with all slots
        # marked as gaps so the marketplace strip can fill them in.
        return {
            "slots": [
                {"role": role, "candidate_id": None, "rationale": None, "is_gap": True}
                for role in ("top", "bottom", "shoes")
            ],
            "rejected": [],
            "summary": _fallback_summary(brief, [], language),
            "detailed_rationale": None,
            "scores": {},
            "model_used": None,
        }

    if gemini_stylist_service is None:
        logger.warning("gemini_stylist_service is None — using deterministic fallback compose")
        return _deterministic_compose(brief, candidates, language)

    # Build a compact JSON description of each candidate for the prompt.
    cand_lines = []
    for c in candidates:
        cand_lines.append(
            "  - " + ", ".join(
                f"{k}={v}" for k, v in {
                    "id": c["candidate_id"],
                    "title": c.get("title"),
                    "category": c.get("category"),
                    "color": c.get("color"),
                    "pattern": c.get("pattern"),
                    "formality": c.get("formality"),
                    "season": c.get("season"),
                }.items() if v
            )
        )
    cand_block = "\n".join(cand_lines)
    constraint_block = _render_constraints(constraints)

    instruction = (
        f"You are a fashion stylist. The user said:\n\"{brief}\"\n\n"
        f"They uploaded {len(candidates)} garment candidates:\n{cand_block}\n\n"
        f"{constraint_block}\n"
        "Choose the BEST single candidate per outfit slot (top, bottom OR dress, "
        "outerwear if needed, shoes, optional accessory). "
        "If two candidates fit the same slot, pick one and mark the other rejected "
        "with reason ('off_brief', 'wrong_category', 'wrong_formality', "
        "'wrong_season', 'color_clash'). "
        "If no candidate fits a slot the brief truly needs, set is_gap=true. "
        f"Reply ONLY with strict JSON in {language} where text fields are appropriate, "
        "schema:\n"
        "{\n"
        '  "slots": [{"role": "top|bottom|dress|outerwear|shoes|accessory", '
        '"candidate_id": "...|null", "rationale": "...", "is_gap": false}],\n'
        '  "rejected": [{"candidate_id": "...", "reason": "off_brief|wrong_category|wrong_formality|wrong_season|color_clash|low_quality", "detail": "..."}],\n'
        '  "scores": {"<candidate_id>": 0.0_to_1.0},\n'
        '  "summary": "one-sentence headline shown in chat",\n'
        '  "detailed_rationale": "2-4 sentences explaining the look"\n'
        "}\n"
    )

    try:
        out = await gemini_stylist_service.advise(
            session_id=f"compose-{uuid.uuid4().hex[:8]}",
            user_text=instruction,
            image_base64=None,
            user_preferences_block=user_preferences_block,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Composer LLM call failed: %s — falling back", repr(exc)[:160])
        return _deterministic_compose(brief, candidates, language)

    parsed = _extract_json(out) if out else None
    if not parsed:
        return _deterministic_compose(brief, candidates, language)

    # Sanitize: drop rejected entries whose candidate_id we don't know
    valid_ids = {c["candidate_id"] for c in candidates}
    parsed["rejected"] = [
        r for r in parsed.get("rejected", [])
        if isinstance(r, dict) and r.get("candidate_id") in valid_ids
    ]
    # Sanitize slots
    cleaned_slots: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for s in parsed.get("slots", []):
        if not isinstance(s, dict):
            continue
        role = (s.get("role") or "").lower()
        if role not in {"top", "bottom", "dress", "outerwear", "shoes", "accessory", "bag", "headwear"}:
            continue
        if role in seen_roles:
            continue
        seen_roles.add(role)
        cid = s.get("candidate_id")
        if cid not in valid_ids:
            cid = None
        cleaned_slots.append(
            {
                "role": role,
                "candidate_id": cid,
                "rationale": s.get("rationale") or None,
                "is_gap": bool(s.get("is_gap")) or cid is None,
            }
        )
    parsed["slots"] = cleaned_slots or _deterministic_compose(brief, candidates, language)["slots"]
    parsed["model_used"] = settings.DEFAULT_STYLIST_MODEL
    return parsed


def _deterministic_compose(
    brief: str, candidates: list[dict[str, Any]], language: str
) -> dict[str, Any]:
    """LLM-free fallback: bucket by category, pick the first per slot."""
    buckets: dict[str, dict[str, Any]] = {}
    for c in candidates:
        cat = (c.get("category") or "").lower()
        slot = _category_to_slot(cat)
        if slot and slot not in buckets:
            buckets[slot] = c

    slots: list[dict[str, Any]] = []
    for role in SLOT_PRIORITY:
        if role in buckets:
            slots.append({
                "role": role,
                "candidate_id": buckets[role]["candidate_id"],
                "rationale": f"Selected {buckets[role].get('title') or role}.",
                "is_gap": False,
            })
    # Always make sure top + bottom (or a dress) is present, even if as a gap.
    has_dress = any(s["role"] == "dress" for s in slots)
    if not has_dress:
        if not any(s["role"] == "top" for s in slots):
            slots.append({"role": "top", "candidate_id": None, "rationale": None, "is_gap": True})
        if not any(s["role"] == "bottom" for s in slots):
            slots.append({"role": "bottom", "candidate_id": None, "rationale": None, "is_gap": True})
    if not any(s["role"] == "shoes" for s in slots):
        slots.append({"role": "shoes", "candidate_id": None, "rationale": None, "is_gap": True})
    return {
        "slots": slots,
        "rejected": [],
        "summary": _fallback_summary(brief, slots, language),
        "detailed_rationale": None,
        "scores": {c["candidate_id"]: 0.6 for c in candidates},
        "model_used": "deterministic-fallback",
    }


def _category_to_slot(cat: str) -> str | None:
    if not cat:
        return None
    cat = cat.lower()
    if "dress" in cat:
        return "dress"
    if cat in {"top", "shirt", "tshirt", "t-shirt", "blouse", "sweater", "knit", "tee"}:
        return "top"
    if cat in {"bottom", "pants", "trousers", "jeans", "shorts", "skirt"}:
        return "bottom"
    if cat in {"outerwear", "jacket", "coat", "blazer"}:
        return "outerwear"
    if cat in {"shoes", "footwear", "sneakers", "boots", "heels"}:
        return "shoes"
    if cat in {"bag", "handbag", "backpack", "purse"}:
        return "bag"
    if cat in {"hat", "cap", "headwear", "scarf"}:
        return "headwear"
    if cat in {"accessory", "jewellery", "jewelry", "belt", "watch"}:
        return "accessory"
    return None


# ─── 4) closet gap fill ─────────────────────────────────────
async def _fill_gaps_from_closet(
    *,
    user_id: str | None,
    slots: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    brief: str,
) -> None:
    """For every is_gap slot, try to fill it with the user's closet."""
    if not user_id:
        return
    db = get_db()
    for slot in slots:
        if not slot.get("is_gap"):
            continue
        role = slot["role"]
        cat_filter = _slot_to_category_query(role)
        if not cat_filter:
            continue
        item = await repos.find_one(
            db.closet_items,
            {"user_id": user_id, **cat_filter},
            sort=[("wear_count", 1), ("created_at", -1)],
        )
        if not item:
            continue
        cid = str(uuid.uuid4())
        candidates.append(
            {
                "candidate_id": cid,
                "source": "closet",
                "image_data_url": item.get("thumbnail_data_url")
                or item.get("segmented_image_url")
                or item.get("original_image_url"),
                "closet_item_id": item.get("id"),
                "title": item.get("title") or item.get("name"),
                "category": item.get("category"),
                "sub_category": item.get("sub_category"),
                "color": item.get("color"),
                "pattern": item.get("pattern"),
                "material": item.get("material"),
                "brand": item.get("brand"),
                "formality": item.get("formality"),
                "season": item.get("season"),
                "tags": item.get("tags") or [],
                "quality_score": 0.85,
                "brief_match_score": 0.7,
                "dedup_group_id": None,
            }
        )
        slot["candidate_id"] = cid
        slot["rationale"] = f"From your closet: {item.get('title') or 'an item that matches'}."
        slot["is_gap"] = False


def _slot_to_category_query(role: str) -> dict[str, Any] | None:
    if role == "top":
        return {"category": {"$in": ["top", "shirt", "tshirt", "blouse", "sweater"]}}
    if role == "bottom":
        return {"category": {"$in": ["bottom", "pants", "jeans", "shorts", "skirt", "trousers"]}}
    if role == "dress":
        return {"category": "dress"}
    if role == "outerwear":
        return {"category": {"$in": ["outerwear", "jacket", "coat", "blazer"]}}
    if role == "shoes":
        return {"category": {"$in": ["shoes", "footwear", "sneakers", "boots", "heels"]}}
    if role == "bag":
        return {"category": {"$in": ["bag", "handbag", "backpack", "purse"]}}
    if role == "headwear":
        return {"category": {"$in": ["hat", "cap", "headwear", "scarf"]}}
    if role == "accessory":
        return {"category": "accessory"}
    return None


# ─── helpers ─────────────────────────────────────────────────
_JSON_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _extract_json(payload: dict[str, Any] | str | None) -> dict[str, Any] | None:
    """The Stylist returns a StylistAdvice dict; we asked it for raw JSON in
    ``transcript`` / ``reasoning_summary``. Try to recover."""
    if not payload:
        return None
    text: str | None = None
    if isinstance(payload, dict):
        for key in ("transcript", "reasoning_summary", "spoken_reply", "summary"):
            v = payload.get(key)
            if v and isinstance(v, str):
                text = v
                break
    elif isinstance(payload, str):
        text = payload
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    import json
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def _render_constraints(constraints: dict[str, Any]) -> str:
    parts = []
    if constraints.get("budget_cents"):
        parts.append(f"Budget: ≤{constraints['budget_cents'] / 100:.0f} {constraints.get('currency', 'USD')}")
    if constraints.get("dress_code"):
        parts.append(f"Dress code: {constraints['dress_code']}")
    if constraints.get("season"):
        parts.append(f"Season: {constraints['season']}")
    if constraints.get("must_include"):
        parts.append(f"Must include: {', '.join(constraints['must_include'])}")
    if constraints.get("avoid"):
        parts.append(f"Avoid: {', '.join(constraints['avoid'])}")
    return ("Constraints: " + "; ".join(parts)) if parts else ""


def _fallback_summary(brief: str, slots: list[dict[str, Any]], language: str) -> str:
    used = sum(1 for s in slots if not s.get("is_gap"))
    gaps = sum(1 for s in slots if s.get("is_gap"))
    if language.lower().startswith("he"):
        return f"הרכבתי שילוב ({used} פריטים, {gaps} חסרים) על בסיס: \"{brief[:80]}\"."
    return f"Composed an outfit with {used} pieces, {gaps} open slot(s)."
