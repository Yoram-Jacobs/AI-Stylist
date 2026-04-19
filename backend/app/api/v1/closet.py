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
from app.models.schemas import ClosetItem, Formality, RetailMetadata, Source
from app.services import repos
from app.services.auth import get_current_user
from app.services.gemini_image_service import gemini_image_service
from app.services.hf_segmentation import hf_segmentation_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/closet", tags=["closet"])


class CreateItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Source = "Private"
    category: str
    sub_category: str | None = None
    title: str
    brand: str | None = None
    size: str | None = None
    color: str | None = None
    material: str | None = None
    pattern: str | None = None
    season: list[str] = Field(default_factory=list)
    formality: Formality | None = None
    cultural_tags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Accept EITHER a remote URL OR inline base64 bytes (for Phase 2 inline uploads).
    original_image_url: str | None = None
    image_base64: str | None = None
    image_mime: str = "image/jpeg"
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
        category=payload.category,
        sub_category=payload.sub_category,
        title=payload.title,
        brand=payload.brand,
        size=payload.size,
        color=payload.color,
        material=payload.material,
        pattern=payload.pattern,
        season=payload.season,
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

    await repos.insert(db.closet_items, doc)
    return doc


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
    if gemini_image_service is None:
        raise HTTPException(503, "Gemini image service not configured")
    try:
        edit = await gemini_image_service.edit(source_url, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nano Banana edit failed for item %s: %s", item_id, exc)
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
