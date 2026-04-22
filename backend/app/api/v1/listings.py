"""Listings CRUD + fee preview."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.db.database import get_db
from app.models.schemas import (
    Condition,
    FinancialMetadata,
    Listing,
    ListingMode,
    ListingSource,
    ListingStatus,
)
from app.services import repos
from app.services.auth import get_current_user, get_current_user_optional
from app.services.fashion_clip import fashion_clip_service
from app.services.fees import compute_fees

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/listings", tags=["listings"])


class CreateListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    closet_item_id: str | None = None
    source: ListingSource = "Shared"
    mode: ListingMode = "sell"
    title: str
    description: str | None = None
    category: str
    size: str | None = None
    condition: Condition = "good"
    images: list[str] = Field(default_factory=list)
    location: dict[str, Any] | None = None
    ships_to: list[str] = Field(default_factory=list)
    list_price_cents: int = Field(ge=0)
    currency: str = "USD"


class UpdateListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    description: str | None = None
    category: str | None = None
    size: str | None = None
    condition: Condition | None = None
    images: list[str] | None = None
    location: dict[str, Any] | None = None
    ships_to: list[str] | None = None
    list_price_cents: int | None = None
    status: ListingStatus | None = None


@router.get("/fee-preview")
async def fee_preview(
    list_price_cents: int = Query(ge=0),
) -> dict[str, Any]:
    return compute_fees(list_price_cents).to_dict()


@router.post("", status_code=201)
async def create_listing(
    payload: CreateListingIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    # If linking to a closet item, ensure ownership and mark it Shared/Retail.
    closet_item = None
    if payload.closet_item_id:
        closet_item = await repos.find_one(
            db.closet_items,
            {"id": payload.closet_item_id, "user_id": user["id"]},
        )
        if not closet_item:
            raise HTTPException(404, "Linked closet item not found")

    fees = compute_fees(payload.list_price_cents)
    financial = FinancialMetadata(
        list_price_cents=payload.list_price_cents,
        currency=payload.currency,
        platform_fee_percent=fees.platform_fee_percent,
        estimated_seller_net_cents=fees.seller_net_cents,
    )
    listing = Listing(
        closet_item_id=payload.closet_item_id,
        seller_id=user["id"],
        source=payload.source,
        mode=payload.mode,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        size=payload.size,
        condition=payload.condition,
        images=payload.images,
        location=payload.location,
        ships_to=payload.ships_to,
        financial_metadata=financial,
    )
    doc = listing.model_dump()
    await repos.insert(db.listings, doc)

    # Transition the closet_item's source (Private → Shared/Retail).
    if closet_item and closet_item.get("source") == "Private":
        await db.closet_items.update_one(
            {"id": closet_item["id"]},
            {"$set": {"source": payload.source,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

    return doc


@router.get("")
async def browse_listings(
    source: ListingSource | None = Query(default=None),
    category: str | None = Query(default=None),
    mode: ListingMode | None = Query(default=None),
    seller_id: str | None = Query(default=None),
    min_price_cents: int | None = Query(default=None, ge=0),
    max_price_cents: int | None = Query(default=None, ge=0),
    status: ListingStatus = Query(default="active"),
    limit: int = Query(default=30, le=100),
    skip: int = Query(default=0, ge=0),
    user: dict | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    db = get_db()
    query: dict[str, Any] = {"status": status}
    if source:
        query["source"] = source
    if category:
        query["category"] = category
    if mode:
        query["mode"] = mode
    if seller_id:
        query["seller_id"] = seller_id
    if min_price_cents is not None:
        query.setdefault("financial_metadata.list_price_cents", {})["$gte"] = (
            min_price_cents
        )
    if max_price_cents is not None:
        query.setdefault("financial_metadata.list_price_cents", {})["$lte"] = (
            max_price_cents
        )

    items = await repos.find_many(
        db.listings, query, sort=[("created_at", -1)], limit=limit, skip=skip
    )
    total = await repos.count(db.listings, query)
    return {"items": items, "total": total, "limit": limit, "skip": skip}


@router.get("/{listing_id}")
async def get_listing(listing_id: str) -> dict[str, Any]:
    listing = await repos.find_one(get_db().listings, {"id": listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    # bump views (fire-and-forget)
    try:
        await get_db().listings.update_one(
            {"id": listing_id}, {"$inc": {"views": 1}}
        )
    except Exception:  # noqa: BLE001
        pass
    return listing


@router.get("/{listing_id}/similar")
async def get_similar_listings(
    listing_id: str,
    limit: int = Query(default=6, ge=1, le=24),
    min_score: float = Query(default=0.22, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Return listings whose underlying closet item is visually similar.

    Powered by FashionCLIP embeddings persisted on each closet item.
    Falls back to category-only matching when embeddings are missing so
    the UI can still show something useful on legacy rows.
    """
    db = get_db()
    seed = await repos.find_one(db.listings, {"id": listing_id})
    if not seed:
        raise HTTPException(404, "Listing not found")
    seed_item_id = seed.get("closet_item_id")
    seed_item: dict[str, Any] | None = None
    if seed_item_id:
        seed_item = await repos.find_one(db.closet_items, {"id": seed_item_id})
    seed_vec = (seed_item or {}).get("clip_embedding")

    # Candidates: all active listings in the same marketplace (including
    # other categories) except this listing itself.
    cand_query: dict[str, Any] = {
        "status": "active",
        "id": {"$ne": listing_id},
    }
    candidates = await repos.find_many(
        db.listings, cand_query, sort=[("created_at", -1)], limit=500
    )
    if not candidates:
        return {"items": [], "total": 0, "mode": "none"}

    # Batch-fetch the embeddings for every candidate's underlying item.
    item_ids = [c["closet_item_id"] for c in candidates if c.get("closet_item_id")]
    vec_map: dict[str, list[float]] = {}
    cat_map: dict[str, str | None] = {}
    if item_ids:
        docs = await repos.find_many(
            db.closet_items,
            {"id": {"$in": item_ids}},
            sort=[("created_at", -1)],
            limit=len(item_ids),
        )
        for d in docs:
            ce = d.get("clip_embedding")
            if isinstance(ce, list) and ce:
                vec_map[d["id"]] = ce
            cat_map[d["id"]] = d.get("category")

    mode = "embedding"
    scored: list[dict[str, Any]] = []
    if fashion_clip_service is not None and seed_vec:
        for c in candidates:
            vec = vec_map.get(c.get("closet_item_id") or "")
            if not vec:
                continue
            score = fashion_clip_service.cosine(seed_vec, vec)
            if score < min_score:
                continue
            c2 = dict(c)
            c2["_score"] = round(score, 4)
            scored.append(c2)
        scored.sort(key=lambda r: r["_score"], reverse=True)
    else:
        # Embedding fallback: show active listings in the same category,
        # newest first. Marks the response so the UI can render a subtler
        # "popular in this category" label rather than "items like this".
        mode = "category"
        seed_cat = (seed_item or {}).get("category") or seed.get("category")
        for c in candidates:
            cat = cat_map.get(c.get("closet_item_id") or "") or c.get("category")
            if seed_cat and cat and cat != seed_cat:
                continue
            scored.append(dict(c))
    return {
        "items": scored[: max(1, limit)],
        "total": len(scored),
        "mode": mode,
        "seed_has_embedding": bool(seed_vec),
    }


@router.patch("/{listing_id}")
async def update_listing(
    listing_id: str,
    payload: UpdateListingIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    db = get_db()
    listing = await repos.find_one(
        db.listings, {"id": listing_id, "seller_id": user["id"]}
    )
    if not listing:
        raise HTTPException(404, "Listing not found")
    patch = payload.model_dump(exclude_none=True)
    if "list_price_cents" in patch:
        fees = compute_fees(patch["list_price_cents"])
        patch["financial_metadata.list_price_cents"] = patch.pop("list_price_cents")
        patch["financial_metadata.estimated_seller_net_cents"] = fees.seller_net_cents
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.listings.update_one({"id": listing_id}, {"$set": patch})
    return await repos.find_one(db.listings, {"id": listing_id}) or {}


@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: str, user: dict = Depends(get_current_user)
) -> Response:
    deleted = await repos.delete(
        get_db().listings, {"id": listing_id, "seller_id": user["id"]}
    )
    if not deleted:
        raise HTTPException(404, "Listing not found")
    return Response(status_code=204)
