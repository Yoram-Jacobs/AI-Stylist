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
