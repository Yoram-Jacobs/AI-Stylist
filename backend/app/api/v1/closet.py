"""Closet CRUD — honours Source Tags (Private/Shared/Retail).

Items default to `source=Private`. Uploading an image triggers a best-effort
Hugging Face SAM segmentation in the background; failures are swallowed
(visible in logs) and the original image URL is retained.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.db.database import get_db
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
from app.services.hf_image_service import hf_image_service
from app.services.hf_segmentation import hf_segmentation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/closet", tags=["closet"])


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
    # Purchase history (optional)
    purchase_price_cents: int | None = None
    purchase_currency: str = "USD"
    purchase_date: str | None = None
    notes: str | None = None
    retail_metadata: RetailMetadata | None = None


class UpdateItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source | None = None
    category: str | None = None
    sub_category: str | None = None
    title: str | None = None
    brand: str | None = None
    size: str | None = None
    color: str | None = None
    material: str | None = None
    pattern: str | None = None
    season: list[str] | None = None
    formality: Formality | None = None
    cultural_tags: list[str] | None = None
    tags: list[str] | None = None
    wear_count: int | None = None
    last_worn_at: str | None = None
    notes: str | None = None


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
    )
    doc = item.model_dump()

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
    if payload.multi:
        try:
            detections = await garment_vision_service.analyze_outfit(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Outfit analysis failed: %s", exc)
            raise HTTPException(
                503,
                "Garment analyzer is temporarily unavailable. Please try again.",
            ) from exc
        items_out: list[dict[str, Any]] = []
        for det in detections:
            analysis = _safe_analysis(dict(det.get("analysis") or {}))
            items_out.append(
                {
                    "label": det.get("label"),
                    "kind": det.get("kind"),
                    "bbox": det.get("bbox"),
                    "crop_base64": det.get("crop_base64"),
                    "crop_mime": det.get("crop_mime", "image/jpeg"),
                    "analysis": analysis,
                }
            )
        # Mirror the first item at the top level so older callers keep working.
        first = items_out[0]["analysis"] if items_out else _safe_analysis({})
        return {"items": items_out, "count": len(items_out), **first}

    # Legacy single-item path (kept for any internal caller that sets multi=False).
    try:
        parsed = await garment_vision_service.analyze(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Garment analysis failed: %s", exc)
        raise HTTPException(
            503, "Garment analyzer is temporarily unavailable. Please try again."
        ) from exc
    analysis = _safe_analysis(parsed)
    crop_b64 = base64.b64encode(raw).decode("ascii")
    return {
        "items": [
            {
                "label": analysis.get("item_type") or analysis.get("sub_category") or "garment",
                "kind": "garment",
                "bbox": [0, 0, 1000, 1000],
                "crop_base64": crop_b64,
                "crop_mime": "image/jpeg",
                "analysis": analysis,
            }
        ],
        "count": 1,
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
    total = await repos.count(db.closet_items, query)
    return {"items": items, "total": total, "limit": limit, "skip": skip}


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
    patch = payload.model_dump(exclude_none=True)
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
