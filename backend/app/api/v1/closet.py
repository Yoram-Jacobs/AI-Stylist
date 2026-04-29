"""Closet CRUD — honours Source Tags (Private/Shared/Retail).

Items default to `source=Private`. Uploading an image triggers a best-effort
Hugging Face SAM segmentation in the background; failures are swallowed
(visible in logs) and the original image URL is retained.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.db.database import get_db
from app.config import settings
from app.models.schemas import (
    ClosetItem,
    DressCode,
    FinancialMetadata,
    Formality,
    GarmentAnalysis,
    GarmentCondition,
    GarmentGender,
    GarmentQuality,
    GarmentState,
    Listing,
    MarketplaceIntent,
    RetailMetadata,
    Source,
    WeightedTag,
)
from app.services import repos
from app.services.auth import get_current_user
from app.services.fees import compute_fees
from app.services.garment_vision import garment_vision_service
from app.services.fashion_clip import fashion_clip_service
from app.services.hf_image_service import hf_image_service
from app.services.hf_segmentation import hf_segmentation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/closet", tags=["closet"])

# Process-wide guard around the heavy analyze pipeline (SegFormer +
# rembg + Gemini). On RAM-constrained production VPSs (e.g. 3 GB
# Hetzner box) running two of these in parallel reliably OOMs the
# second one inside rembg's onnxruntime session — symptom: the second
# upload silently "lands as-is" with blank fields. Serialising at the
# endpoint layer makes the API safe regardless of how many tabs /
# parallel clients hit it. Sub-crops within a single call still run
# concurrently via the inner Semaphore in `analyze_outfit`.
_ANALYZE_LOCK = asyncio.Semaphore(1)


class CreateItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source = "Private"
    # Descriptive
    name: str | None = None
    title: str
    caption: str | None = None
    # Taxonomy
    category: str
    sub_category: str | None = None
    item_type: str | None = None
    brand: str | None = None
    gender: GarmentGender | None = None
    dress_code: DressCode | None = None
    season: list[str] = Field(default_factory=list)
    tradition: str | None = None
    # Composition
    size: str | None = None
    color: str | None = None
    colors: list[WeightedTag] = Field(default_factory=list)
    material: str | None = None
    fabric_materials: list[WeightedTag] = Field(default_factory=list)
    pattern: str | None = None
    # Quality
    state: GarmentState | None = None
    condition: GarmentCondition | None = None
    quality: GarmentQuality | None = None
    repair_advice: str | None = None
    # Pricing + marketplace intent
    price_cents: int | None = None
    currency: str = "USD"
    marketplace_intent: MarketplaceIntent = "own"
    # Legacy
    formality: Formality | None = None
    cultural_tags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Media
    original_image_url: str | None = None
    image_base64: str | None = None
    image_mime: str = "image/jpeg"
    # Phase Q — Wardrobe Reconstructor (optional; set by /analyze response)
    reconstructed_image_b64: str | None = None
    reconstruction_metadata: dict[str, Any] | None = None
    # Purchase history (optional)
    purchase_price_cents: int | None = None
    purchase_currency: str = "USD"
    purchase_date: str | None = None
    notes: str | None = None
    retail_metadata: RetailMetadata | None = None
    # Phase V6 — DPP data imported via QR scan (optional)
    dpp_data: dict[str, Any] | None = None


class UpdateItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source | None = None
    # Descriptive
    name: str | None = None
    title: str | None = None
    caption: str | None = None
    # Taxonomy
    category: str | None = None
    sub_category: str | None = None
    item_type: str | None = None
    brand: str | None = None
    gender: GarmentGender | None = None
    dress_code: DressCode | None = None
    season: list[str] | None = None
    tradition: str | None = None
    # Composition
    size: str | None = None
    color: str | None = None
    colors: list[WeightedTag] | None = None
    material: str | None = None
    fabric_materials: list[WeightedTag] | None = None
    pattern: str | None = None
    # Quality
    state: GarmentState | None = None
    condition: GarmentCondition | None = None
    quality: GarmentQuality | None = None
    repair_advice: str | None = None
    # Pricing + marketplace intent
    price_cents: int | None = None
    currency: str | None = None
    marketplace_intent: MarketplaceIntent | None = None
    # Legacy
    formality: Formality | None = None
    cultural_tags: list[str] | None = None
    tags: list[str] | None = None
    # Wear tracking
    wear_count: int | None = None
    last_worn_at: str | None = None
    notes: str | None = None
    # Phase Q — reconstruction knobs
    reconstructed_image_url: str | None = None
    reconstruction_metadata: dict[str, Any] | None = None
    # Allow clearing the reconstruction (user can "revert" via Repair UI)
    clear_reconstruction: bool = False


@router.post("", status_code=201)
async def create_item(
    payload: CreateItemIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    raw_bytes: bytes | None = None
    if payload.image_base64:
        try:
            raw_bytes = base64.b64decode(payload.image_base64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Invalid image_base64: {exc}") from exc

    item = ClosetItem(
        user_id=user["id"],
        source=payload.source,
        name=payload.name,
        title=payload.title,
        caption=payload.caption,
        category=payload.category,
        sub_category=payload.sub_category,
        item_type=payload.item_type,
        brand=payload.brand,
        gender=payload.gender,
        dress_code=payload.dress_code,
        season=payload.season,
        tradition=payload.tradition,
        size=payload.size,
        color=payload.color,
        colors=payload.colors,
        material=payload.material,
        fabric_materials=payload.fabric_materials,
        pattern=payload.pattern,
        state=payload.state,
        condition=payload.condition,
        quality=payload.quality,
        repair_advice=payload.repair_advice,
        price_cents=payload.price_cents,
        currency=payload.currency,
        marketplace_intent=payload.marketplace_intent,
        formality=payload.formality,
        cultural_tags=payload.cultural_tags,
        tags=payload.tags,
        original_image_url=payload.original_image_url,
        purchase_price_cents=payload.purchase_price_cents,
        purchase_currency=payload.purchase_currency,
        purchase_date=payload.purchase_date,
        notes=payload.notes,
        retail_metadata=payload.retail_metadata,
        reconstruction_metadata=payload.reconstruction_metadata,
        dpp_data=payload.dpp_data,
    )
    doc = item.model_dump()

    # Phase Q — persist the reconstructed image (data URL) when supplied.
    if payload.reconstructed_image_b64:
        mime = (payload.reconstruction_metadata or {}).get("mime_type", "image/png")
        doc["reconstructed_image_url"] = (
            f"data:{mime};base64,{payload.reconstructed_image_b64}"
        )

    # Best-effort segmentation (non-blocking for POC latency): try once, soft-fail.
    if raw_bytes and hf_segmentation_service is not None:
        try:
            seg = await hf_segmentation_service.segment_garment(raw_bytes)
            if seg.get("image_b64"):
                doc["segmented_image_url"] = (
                    f"data:{seg.get('mime_type', 'image/png')};base64,"
                    f"{seg['image_b64']}"
                )
                doc["segmentation_model"] = seg.get("model_used")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Segmentation skipped for item %s: %s", item.id, exc)

    # Best-effort FashionCLIP embedding: persist a 512-d L2-normalised
    # vector so the closet can later be searched by similarity
    # ("/closet/search") and listings can be matched against each other.
    # Failure is soft \u2014 the item still saves without an embedding.
    if raw_bytes and fashion_clip_service is not None:
        try:
            vec = await fashion_clip_service.embed_image(raw_bytes)
            if vec:
                doc["clip_embedding"] = vec
                doc["clip_model"] = fashion_clip_service.model_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FashionCLIP embedding skipped for item %s: %s", item.id, exc
            )

    # If the user tagged this item for the marketplace, auto-create a listing.
    # Modes: for_sale -> sell, donate -> donate, swap -> swap. 'own' stays private.
    listing_id: str | None = None
    if payload.marketplace_intent in ("for_sale", "donate", "swap"):
        mode_map = {"for_sale": "sell", "donate": "donate", "swap": "swap"}
        mode = mode_map[payload.marketplace_intent]
        list_price = (payload.price_cents or 0) if mode == "sell" else 0
        fees = compute_fees(list_price)
        financial = FinancialMetadata(
            list_price_cents=list_price,
            currency=payload.currency,
            platform_fee_percent=7.0,
            estimated_seller_net_cents=fees.seller_net_cents,
        )
        # Map our fine-grained GarmentCondition to the simpler Listing condition.
        cond_map = {"excellent": "like_new", "good": "good", "fair": "fair", "bad": "fair"}
        listing_condition = cond_map.get(payload.condition or "", "good")
        cover_image = doc.get("original_image_url") or doc.get("segmented_image_url")
        listing = Listing(
            closet_item_id=doc["id"],
            seller_id=user["id"],
            source="Shared",
            mode=mode,
            title=payload.name or payload.title,
            description=payload.caption,
            category=payload.category,
            size=payload.size,
            condition=listing_condition,
            images=[cover_image] if cover_image else [],
            financial_metadata=financial,
            status="active",
        )
        await repos.insert(db.listings, listing.model_dump())
        listing_id = listing.id
        doc["listing_id"] = listing_id
        # Lift privacy so the stylist engine also sees it as Shared.
        doc["source"] = "Shared"

    await repos.insert(db.closet_items, doc)
    return doc


class AnalyzeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_base64: str | None = None
    image_url: str | None = None
    # When True (default), run the multi-item detect\u2192crop\u2192analyse pipeline
    # so a single outfit photo expands into one card per garment / accessory.
    # Set False to force a single, whole-frame analysis (legacy behaviour).
    multi: bool = True


def _apply_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
    parsed.setdefault("category", "Top")
    parsed.setdefault("pattern", "solid")
    parsed.setdefault("gender", "unisex")
    parsed.setdefault("dress_code", "casual")
    parsed.setdefault("state", "used")
    parsed.setdefault("condition", "good")
    parsed.setdefault("quality", "mid")
    return parsed


def _safe_analysis(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate through Pydantic; fall back to a minimal shape on error."""
    try:
        return GarmentAnalysis(**_apply_defaults(parsed)).model_dump()
    except Exception:  # noqa: BLE001
        return GarmentAnalysis(
            title=parsed.get("title") or "Unnamed garment"
        ).model_dump()


@router.post("/analyze")
async def analyze_item_image(
    payload: AnalyzeIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """**The Eyes** \u2014 auto-fill every Add-Item field from a garment photo.

    Returns an object with an ``items`` array. Each entry represents one
    detected garment / accessory / jewelry piece with its own cropped
    preview and full auto-fill payload. When the photo only contains a
    single item, the array has one entry (and the top-level legacy
    fields are mirrored from that single analysis for backward
    compatibility).
    """
    if garment_vision_service is None:
        raise HTTPException(503, "Garment analyzer not configured")
    if not payload.image_base64 and not payload.image_url:
        raise HTTPException(400, "image_base64 or image_url is required")

    raw: bytes | None = None
    if payload.image_base64:
        try:
            raw = base64.b64decode(payload.image_base64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Invalid image_base64: {exc}") from exc
    elif payload.image_url:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as c:
            resp = await c.get(payload.image_url, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.content
    if not raw:
        raise HTTPException(400, "Could not load image bytes")

    # Multi-item pipeline (default). Degrades gracefully to single.
    user_lang = (user or {}).get("preferred_language") or "en"
    if payload.multi:
        try:
            async with _ANALYZE_LOCK:
                detections = await garment_vision_service.analyze_outfit(raw, language=user_lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Outfit analysis failed: %r", exc)
            raise HTTPException(
                503,
                "Garment analyzer is temporarily unavailable. Please try again.",
            ) from exc
        items_out: list[dict[str, Any]] = []
        dropped_unidentifiable = 0
        from app.services.garment_vision import _is_unidentifiable
        from app.services.duplicate_detection import find_potential_duplicate

        for det in detections:
            analysis = _safe_analysis(dict(det.get("analysis") or {}))
            if _is_unidentifiable(analysis):
                dropped_unidentifiable += 1
                continue
            # Hint to the frontend if this analysed garment looks like
            # something the user already owns. The frontend uses this
            # to show a "Already in closet — add anyway?" modal before
            # the user lands on the editable card.
            try:
                duplicate = await find_potential_duplicate(user["id"], analysis)
            except Exception as exc:  # noqa: BLE001
                logger.warning("duplicate detection failed: %r", exc)
                duplicate = None
            items_out.append(
                {
                    "label": det.get("label"),
                    "kind": det.get("kind"),
                    "bbox": det.get("bbox"),
                    "crop_base64": det.get("crop_base64"),
                    "crop_mime": det.get("crop_mime", "image/jpeg"),
                    "analysis": analysis,
                    "potential_duplicate": duplicate,
                }
            )
        if dropped_unidentifiable:
            logger.info(
                "/analyze: dropped %d unidentifiable item(s)",
                dropped_unidentifiable,
            )
        # If everything was rejected, surface a clean 422 so the
        # frontend can show "couldn't recognise any garment in this
        # photo" instead of saving an empty card.
        if not items_out:
            raise HTTPException(
                422,
                "We couldn't identify any garment in this photo. "
                "Please try a clearer, well-lit shot.",
            )
        # Mirror the first item at the top level so older callers keep working.
        first = items_out[0]["analysis"] if items_out else _safe_analysis({})
        return {"items": items_out, "count": len(items_out), **first}

    # Legacy single-item path (kept for any internal caller that sets multi=False).
    try:
        async with _ANALYZE_LOCK:
            parsed = await garment_vision_service.analyze(raw, language=user_lang)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Garment analysis failed: %r", exc)
        raise HTTPException(
            503, "Garment analyzer is temporarily unavailable. Please try again."
        ) from exc
    analysis = _safe_analysis(parsed)
    from app.services.garment_vision import _is_unidentifiable

    if _is_unidentifiable(analysis):
        raise HTTPException(
            422,
            "We couldn't identify any garment in this photo. "
            "Please try a clearer, well-lit shot.",
        )
    crop_b64 = base64.b64encode(raw).decode("ascii")
    # Same duplicate hint as the multi-item path.
    from app.services.duplicate_detection import find_potential_duplicate

    try:
        potential_duplicate = await find_potential_duplicate(user["id"], analysis)
    except Exception as exc:  # noqa: BLE001
        logger.warning("duplicate detection failed: %r", exc)
        potential_duplicate = None
    return {
        "items": [
            {
                "label": analysis.get("item_type") or analysis.get("sub_category") or "garment",
                "kind": "garment",
                "bbox": [0, 0, 1000, 1000],
                "crop_base64": crop_b64,
                "crop_mime": "image/jpeg",
                "analysis": analysis,
                "potential_duplicate": potential_duplicate,
            }
        ],
        "count": 1,
        **analysis,
    }


@router.get("/analyze/version", include_in_schema=False)
async def analyze_version() -> dict[str, Any]:
    """Public, unauth code-version probe. Returns feature-presence
    booleans + a live rembg health check. No secrets, no LLM calls,
    no DB hits. Safe to expose.
    """
    markers: dict[str, bool | str] = {}
    try:
        from app.services import clothing_parser as _cp

        markers["_postprocess_mask"] = hasattr(_cp, "_postprocess_mask")
        markers["bbox_to_pixels"] = hasattr(_cp, "bbox_to_pixels")
        markers["apply_alpha_intersection"] = hasattr(
            _cp, "apply_alpha_intersection"
        )
        # Confirms the over-cropping regression fix is live: graphic-print
        # t-shirts no longer get split into N shredded "Upper-clothes"
        # instances when their print breaks the SegFormer mask continuity.
        markers["single_instance_classes_v1"] = hasattr(
            _cp, "_SINGLE_INSTANCE_CLASSES"
        )
    except Exception as exc:  # noqa: BLE001
        markers["clothing_parser_error"] = repr(exc)
    try:
        from app.services.garment_vision import _looks_already_cropped as _lac

        synthetic = [
            {"label": "Upper-clothes", "kind": "top", "bbox": [134, 49, 410, 441]},
            {"label": "Dress", "kind": "dress", "bbox": [120, 190, 833, 928]},
        ]
        markers["already_cropped_heuristic_v2"] = bool(_lac(synthetic))
    except Exception as exc:  # noqa: BLE001
        markers["heuristic_error"] = repr(exc)

    # Sanity marker: the analyze endpoint serialises heavy ML work
    # behind a process-wide semaphore. Confirms a deploy that includes
    # the batch-upload OOM fix landed on the VPS.
    markers["analyze_serial_lock"] = "_ANALYZE_LOCK" in globals()

    # Expose which ML path is live so the user can tell at a glance
    # whether dressapp.co is running the full-fat local stack or the
    # Emergent host is running the HF/Gemini fallback path.
    markers["use_local_clothing_parser"] = bool(
        getattr(settings, "USE_LOCAL_CLOTHING_PARSER", False)
    )
    markers["auto_matte_crops"] = bool(
        getattr(settings, "AUTO_MATTE_CROPS", False)
    )
    try:
        from app.config import _HAS_LOCAL_ML, _HAS_REMBG  # type: ignore

        markers["torch_installed"] = bool(_HAS_LOCAL_ML)
        markers["rembg_installed"] = bool(_HAS_REMBG)
    except Exception:  # noqa: BLE001
        pass

    # --- NEW: live rembg health probe ---
    # Generates two test images (256x256 sanity + 2000x2000 real-world
    # scale) and runs the FULL matte_crop pipeline on each. The 2K test
    # mirrors what your camera/phone uploads look like — if rembg silently
    # fails on full-resolution input (OOM, timeout, opacity rejection),
    # this is where we'll see it.
    rembg_probe: dict[str, Any] = {
        "auto_matte_crops_enabled": bool(settings.AUTO_MATTE_CROPS),
        "rembg_model": settings.BACKGROUND_MATTING_REMBG_MODEL,
        "max_edge_setting": settings.BACKGROUND_MATTING_MAX_EDGE,
    }
    try:
        from PIL import Image, ImageDraw
        import io
        import asyncio as _asyncio
        import numpy as _np
        import time as _time
        from app.services import background_matting

        async def _probe_one(size: int) -> dict[str, Any]:
            buf = io.BytesIO()
            img = Image.new("RGB", (size, size), (240, 240, 240))
            ImageDraw.Draw(img).rectangle(
                [int(size * 0.25), int(size * 0.25), int(size * 0.75), int(size * 0.75)],
                fill=(40, 90, 200),
            )
            img.save(buf, format="JPEG", quality=85)
            test_bytes = buf.getvalue()
            t0 = _time.time()
            try:
                result = await _asyncio.wait_for(
                    background_matting.matte_crop(test_bytes), timeout=90.0
                )
            except _asyncio.TimeoutError:
                return {"ok": False, "reason": "timeout_90s", "input_size": size}
            dt = round(_time.time() - t0, 1)
            if not result:
                return {"ok": False, "reason": "matte_crop_returned_None", "elapsed_s": dt, "input_size": size}
            try:
                out_im = Image.open(io.BytesIO(result)).convert("RGBA")
                a = _np.array(out_im)[:, :, 3]
                opaque = float((a > 32).sum()) / float(max(1, a.size))
                return {
                    "ok": opaque > 0.05,
                    "elapsed_s": dt,
                    "opaque_ratio": round(opaque, 3),
                    "input_size": size,
                    "output_dimensions": list(out_im.size),
                    "png_bytes": len(result),
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "reason": "decode_failed", "error": repr(exc)[:160]}

        rembg_probe["small_256"] = await _probe_one(256)
        rembg_probe["large_2000"] = await _probe_one(2000)
        rembg_probe["ok"] = bool(
            rembg_probe["small_256"].get("ok")
            and rembg_probe["large_2000"].get("ok")
        )
    except Exception as exc:  # noqa: BLE001
        rembg_probe["ok"] = False
        rembg_probe["error"] = repr(exc)[:300]
    markers["rembg_probe"] = rembg_probe
    return markers


@router.get("/analyze/diag")
async def analyze_diag(
    user: dict = Depends(get_current_user),  # noqa: ARG001 — auth-gate only
) -> dict[str, Any]:
    """Diagnostic — does a minimal real Gemini call with a 32x32 test
    image and returns the FULL provider response or error. Helps tell
    apart "API key revoked" / "API not enabled" / "key has referer
    restrictions" / "model not accessible" without grepping logs.

    Auth-gated so it can't be used for free LLM calls by anonymous traffic.
    """
    out: dict[str, Any] = {
        "service_initialised": garment_vision_service is not None,
        "provider": settings.GARMENT_VISION_PROVIDER,
        "model": settings.GARMENT_VISION_MODEL,
        "crop_model": settings.GARMENT_VISION_CROP_MODEL,
        "has_gemini_api_key": bool(settings.GEMINI_API_KEY),
        "has_emergent_llm_key": bool(settings.EMERGENT_LLM_KEY),
    }
    # Code-version markers: presence of these symbols proves the latest
    # cropping/postprocessing code is running in *this* container.
    # If any of them are False, the running container is stale → rebuild.
    code_markers: dict[str, bool] = {}
    try:
        from app.services import clothing_parser as _cp

        code_markers["_postprocess_mask"] = hasattr(_cp, "_postprocess_mask")
        code_markers["bbox_to_pixels"] = hasattr(_cp, "bbox_to_pixels")
        code_markers["apply_alpha_intersection"] = hasattr(
            _cp, "apply_alpha_intersection"
        )
    except Exception as exc:  # noqa: BLE001
        code_markers["clothing_parser_import_error"] = repr(exc)
    # Quick functional check: feed _looks_already_cropped a synthetic
    # 2-detection set that mimics the t-shirt photo case (one large
    # "Dress" detection, one small "Upper-clothes"). If the function
    # returns True the new heuristic is live; if False, the running
    # container has the old code that splits patterned t-shirts.
    try:
        from app.services.garment_vision import _looks_already_cropped as _lac

        synthetic = [
            {"label": "Upper-clothes", "kind": "top", "bbox": [134, 49, 410, 441]},
            {"label": "Dress", "kind": "dress", "bbox": [120, 190, 833, 928]},
        ]
        code_markers["already_cropped_heuristic_v2"] = bool(_lac(synthetic))
    except Exception as exc:  # noqa: BLE001
        code_markers["already_cropped_check_error"] = repr(exc)
    out["code_markers"] = code_markers

    if garment_vision_service is None:
        out["status"] = "service_not_initialised"
        return out

    # Build a tiny in-memory JPEG (32x32 grey square) so we exercise the
    # exact image-input path that's failing in production.
    try:
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (180, 180, 180)).save(buf, format="JPEG", quality=85)
        test_bytes = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        out["status"] = "test_image_build_failed"
        out["error"] = repr(exc)
        return out

    # Probe both models the production flow uses (default + crop_model)
    # and capture the FULL exception repr so the user can paste it back
    # without log truncation.
    probes: dict[str, Any] = {}
    for label, model in (
        ("default_model", settings.GARMENT_VISION_MODEL),
        ("crop_model", settings.GARMENT_VISION_CROP_MODEL),
    ):
        try:
            res = await garment_vision_service.analyze(test_bytes, model=model)
            probes[label] = {
                "model": model,
                "ok": True,
                "title": res.get("title"),
            }
        except Exception as exc:  # noqa: BLE001
            probes[label] = {
                "model": model,
                "ok": False,
                "error": repr(exc),  # FULL — no truncation
            }
    out["probes"] = probes
    out["status"] = (
        "all_ok"
        if all(p.get("ok") for p in probes.values())
        else "provider_error"
    )
    return out


# -------------------------------------------------------------------
# Phase V6 — Digital Product Passport (DPP) QR import
# -------------------------------------------------------------------
class ImportDppIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Either the full URL decoded from the QR, or the inline JSON payload
    # embedded directly in the code (some small-data pilots do this).
    qr_payload: str


@router.post("/import-dpp")
async def import_dpp(
    payload: ImportDppIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """**Scan DPP** — decode a QR payload into a draft closet item.

    Accepts an EU Digital Product Passport QR payload (a URL pointing to
    a passport document, or inline JSON). Parses JSON-LD / Schema.org
    `Product` nodes and returns a response shaped like ``/analyze`` so
    the existing Add-Item form can hydrate from it without special-
    casing.
    """
    from app.services.dpp_parser import parse_dpp

    result = await parse_dpp(payload.qr_payload)
    analysis = _safe_analysis(dict(result.get("analysis") or {}))
    dpp_data = result.get("dpp_data") or {}

    crop_bytes: bytes | None = result.get("image_bytes")
    crop_mime: str = result.get("image_mime") or "image/jpeg"
    crop_b64: str | None = (
        base64.b64encode(crop_bytes).decode("ascii") if crop_bytes else None
    )

    item_entry: dict[str, Any] = {
        "label": analysis.get("item_type")
        or analysis.get("sub_category")
        or analysis.get("category")
        or "garment",
        "kind": "garment",
        "bbox": [0, 0, 1000, 1000],
        "crop_base64": crop_b64,
        "crop_mime": crop_mime if crop_b64 else None,
        "analysis": analysis,
        "dpp_data": dpp_data,
        "source": "dpp",
    }

    return {
        "items": [item_entry],
        "count": 1,
        "source": "dpp",
        "has_image": crop_b64 is not None,
        "parse_error": dpp_data.get("parse_error"),
        **analysis,
    }




@router.get("")
async def list_items(
    user: dict = Depends(get_current_user),
    source: Source | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    db = get_db()
    query: dict[str, Any] = {"user_id": user["id"]}
    if source:
        query["source"] = source
    if category:
        query["category"] = category
    if search:
        query["$text"] = {"$search": search}
    items = await repos.find_many(
        db.closet_items, query, sort=[("created_at", -1)], limit=limit, skip=skip
    )

    # --- thumbnail backfill + heavy-field strip ---
    # The raw docs carry *_image_url fields that are full-resolution
    # base64 data URLs (~0.8-1.5 MB each). Returning them verbatim makes
    # the list response balloon to 20-60 MB for a modest closet. We:
    #   1. Lazy-generate a ~15 KB thumbnail_data_url on first read and
    #      persist it back to Mongo so subsequent calls skip the work.
    #   2. Strip the heavy fields from the wire response. The detail
    #      endpoint GET /closet/{id} still returns them in full.
    from app.services import thumbnails as _thumbs

    pairs = await _thumbs.backfill_thumbnails(items)
    if pairs:
        import asyncio as _asyncio
        await _asyncio.gather(
            *[
                db.closet_items.update_one(
                    {"id": _id}, {"$set": {"thumbnail_data_url": _t}}
                )
                for (_id, _t) in pairs
            ]
        )

    _HEAVY_FIELDS = (
        "clip_embedding",
        "crop_base64",
        "crop_mime",
        "variants",
        "reconstruction_metadata",
        "retail_metadata",
        "dpp_data",
    )
    for it in items:
        for k in _HEAVY_FIELDS:
            it.pop(k, None)
        recon = it.get("reconstruction")
        if isinstance(recon, dict):
            recon.pop("image_b64", None)
        raw = it.get("raw")
        if isinstance(raw, dict):
            raw.pop("preview", None)
        # Strip heavy *_image_url fields ONLY when a thumbnail was
        # successfully produced. If the thumbnail pipeline failed for
        # this item, keep one image URL so the grid still has something
        # to show (the user would otherwise see an empty card).
        if isinstance(it.get("thumbnail_data_url"), str):
            it.pop("original_image_url", None)
            it.pop("segmented_image_url", None)
            it.pop("reconstructed_image_url", None)
    total = await repos.count(db.closet_items, query)
    return {"items": items, "total": total, "limit": limit, "skip": skip}


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = None
    image_base64: str | None = None
    limit: int = 24
    min_score: float = 0.15


@router.post("/search")
async def search_closet(
    payload: SearchIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Semantic closet search via FashionCLIP embeddings.

    Accepts *either* a free-text query ("blue flowy summer tops") *or*
    an image (e.g. a screenshot the user wants to find a match for).
    Returns items sorted by cosine similarity, filtered by ``min_score``.
    """
    if fashion_clip_service is None:
        raise HTTPException(503, "Embedding search is not available right now.")
    if not payload.text and not payload.image_base64:
        raise HTTPException(400, "Provide either `text` or `image_base64`.")

    try:
        if payload.image_base64:
            raw = base64.b64decode(payload.image_base64, validate=True)
            q_vec = await fashion_clip_service.embed_image(raw)
        else:
            q_vec = await fashion_clip_service.embed_text(payload.text or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Search embedding failed: %s", exc)
        raise HTTPException(503, "Could not build the search query.") from exc
    if not q_vec:
        raise HTTPException(400, "Empty query.")

    db = get_db()
    # Pull only items that have a stored embedding (others cannot be scored).
    candidates = await repos.find_many(
        db.closet_items,
        {"user_id": user["id"], "clip_embedding": {"$exists": True, "$ne": None}},
        sort=[("created_at", -1)],
        limit=2000,
    )
    scored: list[dict[str, Any]] = []
    for item in candidates:
        vec = item.get("clip_embedding")
        if not isinstance(vec, list) or not vec:
            continue
        score = fashion_clip_service.cosine(q_vec, vec)
        if score < payload.min_score:
            continue
        # Strip the big embedding vector from the response payload.
        slim = {k: v for k, v in item.items() if k != "clip_embedding"}
        slim["_score"] = round(score, 4)
        scored.append(slim)
    scored.sort(key=lambda r: r["_score"], reverse=True)
    return {
        "items": scored[: max(1, payload.limit)],
        "total": len(scored),
        "indexed": len(candidates),
        "model": fashion_clip_service.model_id,
    }


class CompleteOutfitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ids: list[str] = Field(min_length=1, max_length=8)
    include_marketplace: bool = False
    occasion: str | None = None
    limit: int = Field(default=6, ge=1, le=12)
    min_score: float = Field(default=0.10, ge=0.0, le=1.0)
    # When True (default) the server builds an order-weighted centroid:
    # the 1st anchor in `item_ids` gets the heaviest weight, the last
    # gets the lightest (linear decay, normalised to sum=1). Set False
    # for a plain equal-weight mean.
    weighted: bool = True
    # Optional client-supplied coordinates override user.home_location
    # for the weather hook.
    lat: float | None = None
    lng: float | None = None


def _slim_item(it: dict[str, Any]) -> dict[str, Any]:
    """Strip the 512-float embedding + other heavy fields from an item."""
    return {k: v for k, v in it.items() if k not in ("clip_embedding",)}


def _anchor_summary(anchor: dict[str, Any]) -> dict[str, Any]:
    """Compact anchor description used for stylist prompting."""
    return {
        "id": anchor.get("id"),
        "title": anchor.get("title") or anchor.get("name"),
        "category": anchor.get("category"),
        "sub_category": anchor.get("sub_category"),
        "color": anchor.get("color"),
        "material": anchor.get("material"),
        "pattern": anchor.get("pattern"),
        "dress_code": anchor.get("dress_code"),
        "season": anchor.get("season") or [],
    }


@router.post("/complete-outfit")
async def complete_outfit(
    payload: CompleteOutfitIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """**Complete the Outfit** — given 1..N anchor items from the user's
    closet, return ranked complementary items (from the closet and,
    optionally, from the active marketplace) plus a short rationale.

    The score uses FashionCLIP embeddings averaged across the anchors
    (centroid) against every candidate's embedding. Candidates whose
    ``category`` duplicates any anchor's ``category`` are filtered out
    so suggestions are actually *completing* the look rather than
    duplicating it.

    When ``include_marketplace=true`` the endpoint also searches active
    listings (excluding the user's own listings) using the same
    FashionCLIP centroid, then asks Gemini to produce a combined
    rationale grounded in the anchors + shortlist.
    """
    db = get_db()
    # ------- 1. Fetch & validate anchors (preserve client-supplied order) -------
    fetched = await repos.find_many(
        db.closet_items,
        {"id": {"$in": payload.item_ids}, "user_id": user["id"]},
        limit=len(payload.item_ids),
    )
    if not fetched:
        raise HTTPException(404, "None of the selected items were found.")
    if len(fetched) != len(payload.item_ids):
        missing = set(payload.item_ids) - {a["id"] for a in fetched}
        raise HTTPException(
            404,
            f"{len(missing)} item(s) were not found in your closet.",
        )
    # Re-order to match `payload.item_ids` so the first anchor supplied by
    # the client is anchor[0] (drives weighting + stylist narrative).
    by_id = {a["id"]: a for a in fetched}
    anchors = [by_id[i] for i in payload.item_ids if i in by_id]

    # ------- 2. Build anchor centroid (optionally order-weighted) -------
    anchor_vecs: list[tuple[list[float], float]] = []
    if fashion_clip_service is not None:
        n = len(anchors)
        for idx, a in enumerate(anchors):
            vec = a.get("clip_embedding")
            if isinstance(vec, list) and vec:
                if payload.weighted and n > 1:
                    # Linear decay: weight = n-idx, then normalise later.
                    weight = float(n - idx)
                else:
                    weight = 1.0
                anchor_vecs.append((vec, weight))
    anchor_categories = {a.get("category") for a in anchors if a.get("category")}

    centroid: list[float] | None = None
    if anchor_vecs:
        dim = len(anchor_vecs[0][0])
        sums = [0.0] * dim
        total_w = 0.0
        for vec, w in anchor_vecs:
            if len(vec) != dim:
                continue
            for i, x in enumerate(vec):
                sums[i] += float(x) * w
            total_w += w
        if total_w > 0:
            mean = [s / total_w for s in sums]
            # L2-normalise so cosine is still a straight dot product.
            norm = sum(x * x for x in mean) ** 0.5
            if norm > 0:
                centroid = [x / norm for x in mean]

    # ------- 3. Score closet candidates -------
    closet_suggestions: list[dict[str, Any]] = []
    if centroid is not None:
        candidates = await repos.find_many(
            db.closet_items,
            {
                "user_id": user["id"],
                "id": {"$nin": payload.item_ids},
                "clip_embedding": {"$exists": True, "$ne": None},
            },
            sort=[("created_at", -1)],
            limit=2000,
        )
        scored: list[dict[str, Any]] = []
        for c in candidates:
            vec = c.get("clip_embedding")
            if not isinstance(vec, list) or not vec:
                continue
            # Diversity: skip same-category-as-any-anchor items so we
            # actually COMPLETE the look (don't suggest another top
            # when the anchor is already a top).
            if c.get("category") in anchor_categories:
                continue
            score = fashion_clip_service.cosine(centroid, vec)
            if score < payload.min_score:
                continue
            slim = _slim_item(c)
            slim["_score"] = round(score, 4)
            scored.append(slim)
        scored.sort(key=lambda r: r["_score"], reverse=True)
        closet_suggestions = scored[: payload.limit]

    # ------- 4. Marketplace suggestions (opt-in) -------
    market_suggestions: list[dict[str, Any]] = []
    if payload.include_marketplace and centroid is not None:
        listings = await repos.find_many(
            db.listings,
            {"status": "active", "seller_id": {"$ne": user["id"]}},
            sort=[("created_at", -1)],
            limit=1000,
        )
        listing_item_ids = [
            lg.get("closet_item_id") for lg in listings if lg.get("closet_item_id")
        ]
        vec_map: dict[str, list[float]] = {}
        cat_map: dict[str, str | None] = {}
        if listing_item_ids:
            docs = await repos.find_many(
                db.closet_items,
                {"id": {"$in": listing_item_ids}},
                limit=len(listing_item_ids),
            )
            for d in docs:
                ce = d.get("clip_embedding")
                if isinstance(ce, list) and ce:
                    vec_map[d["id"]] = ce
                cat_map[d["id"]] = d.get("category")
        m_scored: list[dict[str, Any]] = []
        for lg in listings:
            cid = lg.get("closet_item_id")
            if not cid:
                continue
            cat = cat_map.get(cid)
            # Same diversity rule for marketplace
            if cat and cat in anchor_categories:
                continue
            vec = vec_map.get(cid)
            if not vec:
                continue
            score = fashion_clip_service.cosine(centroid, vec)
            if score < payload.min_score:
                continue
            lg2 = dict(lg)
            lg2["_score"] = round(score, 4)
            m_scored.append(lg2)
        m_scored.sort(key=lambda r: r["_score"], reverse=True)
        market_suggestions = m_scored[: payload.limit]

    # ------- 5. Weather hook (optional, soft-fail) -------
    from app.services.weather_service import weather_service

    weather_ctx: dict[str, Any] | None = None
    weather_summary_text: str | None = None
    home = user.get("home_location") or {}
    lat = payload.lat if payload.lat is not None else home.get("lat")
    lng = payload.lng if payload.lng is not None else home.get("lng")
    if lat is not None and lng is not None and weather_service is not None:
        try:
            weather_ctx = await weather_service.fetch(
                float(lat),
                float(lng),
                lang=(user.get("preferred_language") or "en"),
            )
            if weather_ctx:
                # Prefer the localized `description` field (e.g. "bewölkt",
                # "מעונן") over the English `condition`. Strip the
                # hardcoded " in " connector to avoid mixing languages.
                localized_cond = (
                    weather_ctx.get("description")
                    or weather_ctx.get("condition")
                    or ""
                )
                parts = [
                    f"{weather_ctx.get('temp_c')}°C",
                    localized_cond,
                    weather_ctx.get("city") or "",
                ]
                weather_summary_text = " · ".join(p for p in parts if p)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Complete-outfit weather fetch failed: %s", exc)

    # ------- 6. Stylist rationale (Gemini) -------
    from app.services.gemini_stylist import gemini_stylist_service

    rationale = ""
    outfit_recommendations: list[dict[str, Any]] = []
    do_dont: list[str] = []
    spoken_reply = ""
    if gemini_stylist_service is not None:
        try:
            anchors_pretty = [_anchor_summary(a) for a in anchors]
            closet_short = [
                {
                    "closet_item_id": s["id"],
                    "title": s.get("title") or s.get("name"),
                    "category": s.get("category"),
                    "color": s.get("color"),
                    "material": s.get("material"),
                    "score": s["_score"],
                }
                for s in closet_suggestions
            ]
            market_short = [
                {
                    "listing_id": lg["id"],
                    "title": lg.get("title"),
                    "category": lg.get("category"),
                    "price_cents": (lg.get("financial_metadata") or {}).get(
                        "list_price_cents"
                    ),
                    "score": lg["_score"],
                }
                for lg in market_suggestions
            ]
            weather_line = (
                f"\nWEATHER: {weather_summary_text}"
                if weather_summary_text
                else ""
            )
            request_text = (
                "Complete this outfit using the user's ANCHOR pieces as the "
                "starting point. The anchors are listed in priority order "
                "(first = most important). Choose complementary items from "
                "the CLOSET_CANDIDATES first (preferred); only reach into "
                "MARKET_CANDIDATES if a key complementary category is "
                "missing. Return ONE or TWO outfit recommendations. In "
                "`why`, explain the reasoning in 1-2 sentences. If weather "
                "context is provided AND the occasion sounds outdoor, "
                "prioritise weather-appropriate layers/footwear and call "
                "that out in the rationale.\n\n"
                f"OCCASION: {payload.occasion or 'unspecified (casual by default)'}"
                f"{weather_line}\n\n"
                f"ANCHORS (priority order): "
                f"{json.dumps(anchors_pretty, ensure_ascii=False)}\n\n"
                f"CLOSET_CANDIDATES: {json.dumps(closet_short, ensure_ascii=False)}\n\n"
                f"MARKET_CANDIDATES: {json.dumps(market_short, ensure_ascii=False)}"
            )
            user_profile = {
                "preferred_language": user.get("preferred_language", "en"),
                "style_profile": user.get("style_profile"),
            }
            advice = await gemini_stylist_service.advise(
                session_id=f"complete-outfit:{user['id']}",
                user_text=request_text,
                image_base64=None,
                weather=weather_ctx,
                user_profile=user_profile,
                closet_summary=closet_short + [{"is_anchor": True, **a} for a in anchors_pretty],
            )
            rationale = advice.get("reasoning_summary", "") or ""
            outfit_recommendations = advice.get("outfit_recommendations", []) or []
            do_dont = advice.get("do_dont", []) or []
            spoken_reply = advice.get("spoken_reply", "") or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("Complete-outfit stylist call failed: %s", exc)
            # Soft-fail: the ranked suggestions are still useful without rationale.

    return {
        "anchors": [_slim_item(a) for a in anchors],
        "closet_suggestions": closet_suggestions,
        "market_suggestions": market_suggestions,
        "rationale": rationale,
        "outfit_recommendations": outfit_recommendations,
        "do_dont": do_dont,
        "spoken_reply": spoken_reply,
        "has_embeddings": centroid is not None,
        "weather_summary": weather_summary_text,
    }


# ------------------------- Phase Q: Wardrobe Reconstructor -------------------------
class RepairItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Optional free-form hint (typed or transcribed from Phase M voice)
    # that the user supplies when the automatic reconstruction missed
    # some detail ("it has ruffles at the hem", "the sleeves are
    # three-quarter, not long", etc.).
    user_hint: str | None = None
    # Ignore the automatic category-drift validator. Useful when the
    # user explicitly wants to retry and accept whatever comes back.
    force: bool = False


@router.post("/{item_id}/clean-background")
async def clean_item_background(
    item_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase V Fix 2 — non-generative background matting.

    Replaces the old "Repair image" generative inpainting (which
    hallucinated matching colours, invented collars, etc.) with a pure
    alpha-matting pipeline powered by BiRefNet (MIT). The matting model
    decides which pixels are garment vs. background; it never invents
    pixels.

    A CLIP faithfulness guard in the matting service rejects matte output
    that drifts too far from the original crop.
    """
    from app.services import background_matting

    db = get_db()
    item = await repos.find_one(
        db.closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")

    crop_url = item.get("segmented_image_url") or item.get("original_image_url")
    if not isinstance(crop_url, str) or not crop_url.startswith("data:"):
        raise HTTPException(
            400, "Item has no cropped image to matte. Re-analyze the item first."
        )
    try:
        _, _, b64_part = crop_url.partition(",")
        crop_bytes = base64.b64decode(b64_part)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Stored crop is corrupted.") from exc

    result = await background_matting.remove_background(crop_bytes)
    if not result.get("image_png"):
        reason = (
            "faithfulness_guard_rejected"
            if result.get("provider") and not result.get("faithful")
            else "matting_unavailable"
        )
        return {
            "item": item,
            "applied": False,
            "reason": reason,
            "detail": (
                "Matting service is currently unreachable or the result "
                "drifted too far from the original; keep the existing crop."
            ),
        }

    out_b64 = base64.b64encode(result["image_png"]).decode("ascii")
    data_url = f"data:image/png;base64,{out_b64}"
    meta = {
        "method": "matting",
        "model": settings.BACKGROUND_MATTING_MODEL,
        "provider": result.get("provider"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.closet_items.update_one(
        {"id": item_id},
        {
            "$set": {
                "reconstructed_image_url": data_url,
                "reconstruction_metadata": meta,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            # Invalidate the cached thumbnail so /closet list regenerates
            # it from the fresh reconstructed image on the next read.
            "$unset": {"thumbnail_data_url": ""},
        },
    )
    item = await repos.find_one(db.closet_items, {"id": item_id}) or item
    return {"item": item, "applied": True, "reconstruction": meta}


class PhotoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_base64: str
    image_mime: str = "image/jpeg"
    # When True (default) run The Eyes pipeline to produce a clean
    # semantic cutout before storing. When False we store the raw upload
    # verbatim (useful when the user already has a product-shot PNG).
    auto_segment: bool = True


@router.post("/{item_id}/photo")
async def set_item_photo(
    item_id: str,
    payload: PhotoIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """**Add or replace** the image of an existing closet item.

    Use-cases:
    * A DPP-imported item has no photo yet — user takes one and attaches it.
    * An existing item has a poor photo — user replaces it with a better one.

    When ``auto_segment`` is True (default), the upload is run through
    The Eyes' single-item pipeline (SegFormer → rembg cutout) so the
    stored photo is already a clean per-garment PNG. Otherwise the raw
    upload is saved as-is.
    """
    db = get_db()
    item = await repos.find_one(
        db.closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")

    try:
        raw = base64.b64decode(payload.image_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid image_base64: {exc}") from exc
    if not raw:
        raise HTTPException(400, "Empty image payload")

    original_data_url = f"data:{payload.image_mime};base64,{payload.image_base64}"
    segmented_data_url: str | None = None
    segmentation_model: str | None = None

    if payload.auto_segment and garment_vision_service is not None:
        # Single-item pipeline: analyse with max_items=1 so we get a
        # semantic cutout of the dominant garment. Never fatal — on any
        # error we just keep the raw upload.
        try:
            items = await garment_vision_service.analyze_outfit(
                raw, max_items=1
            )
            if items:
                first = items[0]
                b64 = first.get("crop_base64")
                mime = first.get("crop_mime") or "image/png"
                if b64:
                    segmented_data_url = f"data:{mime};base64,{b64}"
                    segmentation_model = "the_eyes_single"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "set_item_photo: auto-segment failed (%s); keeping raw",
                repr(exc)[:160],
            )

    update_doc: dict[str, Any] = {
        "original_image_url": original_data_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # Clear any previous reconstruction — it was derived from the
        # old photo and is now stale.
        "reconstructed_image_url": None,
        "reconstruction_metadata": None,
    }
    if segmented_data_url:
        update_doc["segmented_image_url"] = segmented_data_url
        update_doc["segmentation_model"] = segmentation_model
    else:
        update_doc["segmented_image_url"] = None
        update_doc["segmentation_model"] = None

    # Best-effort FashionCLIP re-embedding so semantic search stays fresh.
    if fashion_clip_service is not None:
        try:
            embed_bytes = (
                base64.b64decode(segmented_data_url.split(",", 1)[1])
                if segmented_data_url
                else raw
            )
            vec = await fashion_clip_service.embed_image(embed_bytes)
            if vec:
                update_doc["clip_embedding"] = vec
                update_doc["clip_model"] = fashion_clip_service.model_id
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "set_item_photo: CLIP re-embed failed (%s)", repr(exc)[:120]
            )

    await db.closet_items.update_one(
        {"id": item_id},
        {"$set": update_doc, "$unset": {"thumbnail_data_url": ""}},
    )
    item = await repos.find_one(db.closet_items, {"id": item_id}) or item
    return {
        "item": item,
        "segmented": segmented_data_url is not None,
    }



@router.post("/{item_id}/reanalyze")
async def reanalyze_item(
    item_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-run **The Eyes** on an existing item's stored image and patch
    the analysis-derived fields back onto the document.

    Use-cases:
    * User uploaded a poor photo, replaced it with a better one (with
      ``auto_segment=False`` so the analysis didn't run automatically),
      and now wants the form auto-filled from the new photo.
    * A previous analysis returned junk (regression / model glitch)
      and the user wants a fresh attempt.

    The endpoint preserves user-managed fields (size, price, currency,
    marketplace_intent, notes, cultural_tags, purchase history, ...)
    and only overwrites the fields that The Eyes actually populates
    (title, taxonomy, colours/materials, condition, tags, …).
    """
    if garment_vision_service is None:
        raise HTTPException(503, "Garment analyzer not configured")

    db = get_db()
    item = await repos.find_one(
        db.closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")

    # Prefer the matted/segmented crop because that's what's visible to
    # the user in the closet — analysing the same pixels they're
    # looking at avoids surprises ("why did The Eyes call my shirt a
    # dress?"). Fall back to the original upload otherwise.
    image_url: str | None = (
        item.get("segmented_image_url")
        or item.get("reconstructed_image_url")
        or item.get("original_image_url")
    )
    if not image_url or not image_url.startswith("data:"):
        raise HTTPException(
            400,
            "Item has no stored image to re-analyse. "
            "Replace the photo first.",
        )
    try:
        b64_part = image_url.split(",", 1)[1]
        raw = base64.b64decode(b64_part, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Invalid stored image: {exc}") from exc
    if not raw:
        raise HTTPException(400, "Stored image is empty")

    user_lang = (user or {}).get("preferred_language") or "en"
    try:
        async with _ANALYZE_LOCK:
            parsed = await garment_vision_service.analyze(raw, language=user_lang)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Re-analyse failed: %r", exc)
        raise HTTPException(
            503,
            "Garment analyzer is temporarily unavailable. Please try again.",
        ) from exc

    analysis = _safe_analysis(parsed)
    from app.services.garment_vision import _is_unidentifiable

    if _is_unidentifiable(analysis):
        raise HTTPException(
            422,
            "We couldn't identify a garment in the stored photo. "
            "Try replacing it with a clearer, well-lit shot.",
        )

    # Only overwrite fields The Eyes actually owns. User-managed fields
    # (size, price, currency, intent, notes, purchase history, …) are
    # preserved verbatim so re-analysing doesn't quietly wipe data the
    # user spent time entering.
    OVERWRITE_KEYS = (
        "title",
        "name",
        "caption",
        "category",
        "sub_category",
        "item_type",
        "brand",
        "gender",
        "dress_code",
        "season",
        "tradition",
        "colors",
        "fabric_materials",
        "pattern",
        "state",
        "condition",
        "quality",
        "repair_advice",
        "tags",
    )
    update_doc: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for key in OVERWRITE_KEYS:
        if key in analysis:
            update_doc[key] = analysis[key]

    # Mirror the dominant colour / material into the legacy single-string
    # fields too — older parts of the UI (and downstream Stylist
    # prompts) still read `color` / `material` as scalars.
    colors_list = analysis.get("colors") or []
    if colors_list and isinstance(colors_list, list):
        first_colour = colors_list[0]
        if isinstance(first_colour, dict) and first_colour.get("name"):
            update_doc["color"] = first_colour["name"]
    materials_list = analysis.get("fabric_materials") or []
    if materials_list and isinstance(materials_list, list):
        first_material = materials_list[0]
        if isinstance(first_material, dict) and first_material.get("name"):
            update_doc["material"] = first_material["name"]

    await db.closet_items.update_one(
        {"id": item_id, "user_id": user["id"]},
        {"$set": update_doc},
    )
    item = await repos.find_one(db.closet_items, {"id": item_id}) or item
    return {"item": item, "analysis": analysis}



@router.post("/{item_id}/repair")
async def repair_item_image(
    item_id: str,
    payload: RepairItemIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Rebuild a clean product-grade image for an existing closet item.

    Uses the item's stored analysis fields (title, category, color,
    material, pattern, brand, ...) to drive HF FLUX. An optional
    ``user_hint`` is woven into the prompt so users who noticed a
    missing detail (e.g., "three-quarter sleeves") can steer the
    generation. Falls back cleanly when HF is unavailable.
    """
    from app.services.reconstruction import reconstruct

    db = get_db()
    item = await repos.find_one(
        db.closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")

    analysis: dict[str, Any] = {
        "title": item.get("title"),
        "category": item.get("category"),
        "sub_category": item.get("sub_category"),
        "item_type": item.get("item_type"),
        "color": item.get("color"),
        "material": item.get("material"),
        "pattern": item.get("pattern"),
        "brand": item.get("brand"),
        "dress_code": item.get("dress_code"),
    }

    # Weave the user's hint into the prompt path. The reconstruction
    # service doesn't accept a hint directly, so we smuggle it via a
    # synthetic "item_type" extension that _build_reconstruction_prompt
    # pulls in verbatim.
    if payload.user_hint:
        hint = payload.user_hint.strip()[:240]
        analysis["item_type"] = (
            f"{analysis.get('item_type') or ''} — {hint}"
        ).strip(" —")

    # Use the segmented image as the visual conditioning when present so
    # HF has SOME pixels to look at; otherwise we still fall back to the
    # original crop or an empty byte string (text-to-image path).
    crop_url = item.get("segmented_image_url") or item.get("original_image_url")
    crop_bytes: bytes = b""
    if isinstance(crop_url, str) and crop_url.startswith("data:"):
        try:
            _, _, b64_part = crop_url.partition(",")
            crop_bytes = base64.b64decode(b64_part)
        except Exception:  # noqa: BLE001
            crop_bytes = b""

    out = await reconstruct(
        crop_bytes,
        analysis,
        reasons=["manual_repair"] + (["with_hint"] if payload.user_hint else []),
        validate=not payload.force,
    )
    if out is None:
        raise HTTPException(
            502, "Reconstruction service unavailable. Please try again later."
        )
    if not out.get("validated"):
        return {
            "item": item,
            "reconstruction": out,
            "applied": False,
            "detail": out.get("rejected_reason")
            or "Reconstructor produced an off-category image; keep the existing one.",
        }

    # Persist the reconstruction on the item.
    mime = out.get("mime_type", "image/png")
    data_url = f"data:{mime};base64,{out['image_b64']}"
    meta: dict[str, Any] = {
        "reasons": out.get("reasons", []),
        "prompt": out.get("prompt"),
        "model": out.get("model"),
        "mime_type": mime,
        "user_hint": payload.user_hint,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_doc = {
        "reconstructed_image_url": data_url,
        "reconstruction_metadata": meta,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.closet_items.update_one(
        {"id": item_id},
        {"$set": update_doc, "$unset": {"thumbnail_data_url": ""}},
    )
    item = await repos.find_one(db.closet_items, {"id": item_id}) or item
    return {"item": item, "reconstruction": out, "applied": True}


@router.get("/{item_id}")
async def get_item(
    item_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    item = await repos.find_one(
        get_db().closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.patch("/{item_id}")
async def update_item(
    item_id: str, payload: UpdateItemIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    # ``exclude_none=True`` keeps the PATCH semantics of "send only what you
    # want to change" — a client can e.g. update just `notes` without
    # wiping every other optional field.
    patch = payload.model_dump(exclude_none=True)
    # The `clear_reconstruction` flag is a command, not a value we persist.
    # Pop it + translate into explicit null-sets on the related columns.
    if patch.pop("clear_reconstruction", False):
        patch["reconstructed_image_url"] = None
        patch["reconstruction_metadata"] = None
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await repos.update(
        get_db().closet_items, {"id": item_id, "user_id": user["id"]}, patch
    )
    if not updated:
        raise HTTPException(404, "Item not found")
    return updated


@router.delete("/{item_id}")
async def delete_item(
    item_id: str, user: dict = Depends(get_current_user)
) -> Response:
    deleted = await repos.delete(
        get_db().closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not deleted:
        raise HTTPException(404, "Item not found")
    return Response(status_code=204)


@router.post("/{item_id}/edit-image")
async def edit_item_image(
    item_id: str,
    prompt: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger Gemini Nano Banana image-to-image to generate a variant
    (e.g. 'in navy blue' or 'with short sleeves').

    Stores the variant (as a data URL) in `variants[]` so the client can
    preview it alongside the original.
    """
    db = get_db()
    item = await repos.find_one(
        db.closet_items, {"id": item_id, "user_id": user["id"]}
    )
    if not item:
        raise HTTPException(404, "Item not found")
    source_url = item.get("segmented_image_url") or item.get("original_image_url")
    if not source_url:
        raise HTTPException(400, "No source image on this item")
    if hf_image_service is None:
        raise HTTPException(503, "Image generation service not configured")
    try:
        edit = await hf_image_service.edit(
            source_url,
            prompt,
            garment_metadata={
                "title": item.get("title"),
                "category": item.get("category"),
                "color": item.get("color"),
                "material": item.get("material"),
                "pattern": item.get("pattern"),
                "brand": item.get("brand"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("HF image edit failed for item %s: %s", item_id, exc)
        raise HTTPException(
            503,
            "Image generation is temporarily unavailable. Please try again shortly.",
        ) from exc
    variant_url = (
        f"data:{edit.get('mime_type', 'image/png')};base64,{edit['image_b64']}"
    )
    variants = list(item.get("variants") or [])
    variants.append(
        {
            "prompt": prompt,
            "url": variant_url,
            "model": edit["model_used"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await db.closet_items.update_one(
        {"id": item_id, "user_id": user["id"]}, {"$set": {"variants": variants}}
    )
    return {"variant_url": variant_url, "variants": variants}
