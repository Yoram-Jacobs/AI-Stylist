"""Transactions — create pending records with full financial ledger.

Phase 2 only writes the ledger; Stripe Connect Express checkout + webhook
wiring is Phase 4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.db.database import get_db
from app.models.schemas import (
    StripePointer,
    Transaction,
    TransactionFinancial,
    TxStatus,
)
from app.services import repos
from app.services.auth import get_current_user
from app.services.fees import compute_fees

router = APIRouter(prefix="/transactions", tags=["transactions"])


class CreateTxIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: str


@router.post("", status_code=201)
async def create_transaction(
    payload: CreateTxIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    listing = await repos.find_one(db.listings, {"id": payload.listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.get("status") != "active":
        raise HTTPException(409, "Listing is not active")
    if listing.get("seller_id") == user["id"]:
        raise HTTPException(400, "You cannot buy your own listing")

    gross = int(listing["financial_metadata"]["list_price_cents"])
    fees = compute_fees(gross)
    tx = Transaction(
        listing_id=listing["id"],
        buyer_id=user["id"],
        seller_id=listing["seller_id"],
        currency=listing["financial_metadata"].get("currency", "USD"),
        financial=TransactionFinancial(
            gross_cents=fees.gross_cents,
            stripe_fee_cents=fees.stripe_fee_cents,
            net_after_stripe_cents=fees.net_after_stripe_cents,
            platform_fee_percent=fees.platform_fee_percent,
            platform_fee_cents=fees.platform_fee_cents,
            seller_net_cents=fees.seller_net_cents,
        ),
        stripe=StripePointer(),
        status="pending",
    )
    doc = tx.model_dump()
    await repos.insert(db.transactions, doc)

    # Reserve the listing (Phase 4 will release on payment failure).
    await db.listings.update_one(
        {"id": listing["id"]},
        {"$set": {
            "status": "reserved",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return doc


@router.get("")
async def list_transactions(
    user: dict = Depends(get_current_user),
    role: str = Query(default="all", regex="^(buyer|seller|all)$"),
    status: TxStatus | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    db = get_db()
    query: dict[str, Any] = {}
    if role == "buyer":
        query["buyer_id"] = user["id"]
    elif role == "seller":
        query["seller_id"] = user["id"]
    else:
        query["$or"] = [{"buyer_id": user["id"]}, {"seller_id": user["id"]}]
    if status:
        query["status"] = status
    items = await repos.find_many(
        db.transactions, query, sort=[("created_at", -1)], limit=limit, skip=skip
    )
    total = await repos.count(db.transactions, query)
    return {"items": items, "total": total}


@router.get("/{tx_id}")
async def get_transaction(
    tx_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    tx = await repos.find_one(
        get_db().transactions,
        {
            "id": tx_id,
            "$or": [{"buyer_id": user["id"]}, {"seller_id": user["id"]}],
        },
    )
    if not tx:
        raise HTTPException(404, "Transaction not found")
    return tx
