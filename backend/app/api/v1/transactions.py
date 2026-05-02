"""Transactions — buy ledger + Wave 2 swap & donate pipelines.

The classic ``POST /transactions`` endpoint creates a ``kind="buy"``
record and reserves a listing — kept untouched for backwards compat
with existing PayPal flow paths in ``payments.py``.

Wave 2 adds three transaction kinds-of-flow on top:

* ``POST /transactions/swap`` — swapper offers one of their closet
  items in exchange for a listing. Lister gets an emailed accept/deny
  link signed with a single-use JWT.
* ``POST /transactions/donate`` — recipient claims a donation listing.
  Optional handling-fee path falls back to PayPal; zero-fee path emails
  the donor with accept/deny links.
* ``GET /transactions/action`` — public endpoint hit by the email
  buttons. Verifies the JWT, applies the decision idempotently, and
  redirects the browser to the frontend landing page.
* ``POST /transactions/{id}/confirm-receipt`` — auth'd; either party
  marks the incoming item as received. Once both parties have
  confirmed, the swap completes (closet ownership flips, listings
  close, ``donation_both`` template fires for donations).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from app.db.database import get_db
from app.models.schemas import (
    DonatePointer,
    PayPalPointer,
    StripePointer,
    SwapPointer,
    Transaction,
    TransactionFinancial,
    TxStatus,
)
from app.services import action_tokens, repos
from app.services import email_service as es
from app.services.auth import get_current_user
from app.services.fees import compute_fees

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transactions", tags=["transactions"])

# Public app URL used to build accept/deny links + post-action redirects.
# Falls back to dressapp.co for prod and respects APP_PUBLIC_URL when set
# on dev/staging pods so emails on those environments correctly point
# back at their frontend.
_APP_URL = os.environ.get("APP_PUBLIC_URL", "https://dressapp.co").rstrip("/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------
async def _load_user(db, user_id: str) -> dict[str, Any] | None:
    return await db.users.find_one({"id": user_id}, {"_id": 0})


async def _load_listing_item(db, listing: dict) -> dict[str, Any]:
    """Load the closet-item doc behind a listing for email rendering.

    Always returns a dict, falling back to listing fields if the closet
    record is missing (legacy listings without a linked item).
    """
    item: dict[str, Any] = {}
    if listing.get("closet_item_id"):
        item = await db.closet_items.find_one(
            {"id": listing["closet_item_id"]},
            {
                "_id": 0,
                "title": 1, "brand": 1,
                "thumbnail_data_url": 1,
                "segmented_image_url": 1,
                "original_image_url": 1,
            },
        ) or {}
    item.setdefault("title", listing.get("title"))
    if listing.get("images") and not (
        item.get("thumbnail_data_url")
        or item.get("segmented_image_url")
        or item.get("original_image_url")
    ):
        item["thumbnail_data_url"] = listing["images"][0]
    return item


def _action_url(token: str, decision: str) -> str:
    qs = urlencode({"token": token, "decision": decision})
    return f"{_APP_URL}/api/v1/transactions/action?{qs}"


def _landing_redirect(tx_id: str, status: str, message: str | None = None) -> RedirectResponse:
    params = {"status": status}
    if message:
        params["message"] = message
    return RedirectResponse(
        url=f"{_APP_URL}/transactions/{tx_id}/landing?{urlencode(params)}",
        status_code=303,
    )


# -----------------------------------------------------------------
# Classic buy create (Phase 2 — Stripe ledger; PayPal flow lives in
# payments.py and creates its own Transaction). Left intact for
# backwards compatibility.
# -----------------------------------------------------------------
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
        kind="buy",
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

    await db.listings.update_one(
        {"id": listing["id"]},
        {"$set": {"status": "reserved", "updated_at": _now_iso()}},
    )
    return doc


# -----------------------------------------------------------------
# Wave 2 — Swap propose
# -----------------------------------------------------------------
class SwapProposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: str
    offered_item_id: str


@router.post("/swap", status_code=201)
async def propose_swap(
    payload: SwapProposeIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    listing = await repos.find_one(db.listings, {"id": payload.listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.get("status") != "active":
        raise HTTPException(409, "This listing is no longer accepting offers.")
    if listing.get("seller_id") == user["id"]:
        raise HTTPException(400, "You cannot swap with your own listing.")

    offered = await repos.find_one(
        db.closet_items,
        {"id": payload.offered_item_id, "user_id": user["id"]},
    )
    if not offered:
        raise HTTPException(
            404, "The item you tried to offer wasn't found in your closet."
        )

    # Build a zero-cash Transaction record. We still record fee math at
    # 0 so /transactions reads back consistent dicts across kinds.
    fees = compute_fees(0)
    tx = Transaction(
        listing_id=listing["id"],
        buyer_id=user["id"],
        seller_id=listing["seller_id"],
        kind="swap",
        currency=listing["financial_metadata"].get("currency", "USD"),
        financial=TransactionFinancial(
            gross_cents=0,
            stripe_fee_cents=0,
            net_after_stripe_cents=0,
            platform_fee_percent=fees.platform_fee_percent,
            platform_fee_cents=0,
            seller_net_cents=0,
        ),
        swap=SwapPointer(offered_item_id=offered["id"]),
        status="pending",
    )

    # Mint accept/deny token AFTER tx.id exists. Persist jti so reuse
    # of the same email link is rejected by /action.
    token, jti = action_tokens.mint(
        tx_id=tx.id, role="lister", decision_choices=("accept", "deny"),
        expires_hours=24 * 7,  # generous 7-day window
    )
    tx.swap.action_token_jti = jti
    doc = tx.model_dump()
    await repos.insert(db.transactions, doc)

    # Send swap_request to the lister (best-effort).
    try:
        lister = await _load_user(db, listing["seller_id"]) or {}
        swapper = user
        listing_item = await _load_listing_item(db, listing)
        offered_item = {
            "title": offered.get("title"),
            "brand": offered.get("brand"),
            "thumbnail_data_url": (
                offered.get("thumbnail_data_url")
                or offered.get("segmented_image_url")
                or offered.get("original_image_url")
            ),
        }
        if lister.get("email"):
            await es.swap_request(
                to=lister["email"],
                lister=lister, swapper=swapper,
                listing_item=listing_item, offered_item=offered_item,
                accept_url=_action_url(token, "accept"),
                deny_url=_action_url(token, "deny"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("swap_request email dispatch failed for %s: %s", tx.id, exc)

    return doc


# -----------------------------------------------------------------
# Wave 2 — Donate claim
# -----------------------------------------------------------------
class DonateClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: str
    handling_fee_cents: int | None = None  # 0 / null = free; else PayPal


@router.post("/donate", status_code=201)
async def claim_donation(
    payload: DonateClaimIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    listing = await repos.find_one(db.listings, {"id": payload.listing_id})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing.get("status") != "active":
        raise HTTPException(409, "This donation is no longer available.")
    if listing.get("seller_id") == user["id"]:
        raise HTTPException(400, "You cannot claim your own donation.")
    # Donations have to be flagged via mode=donate; if the lister forgot
    # we still let it through but log so admins can clean up.
    if listing.get("mode") != "donate":
        logger.info(
            "donate claim on non-donate listing %s mode=%s",
            listing["id"], listing.get("mode"),
        )

    fee = max(0, int(payload.handling_fee_cents or 0))
    fees = compute_fees(fee)
    tx = Transaction(
        listing_id=listing["id"],
        buyer_id=user["id"],
        seller_id=listing["seller_id"],
        kind="donate",
        currency=listing["financial_metadata"].get("currency", "USD"),
        financial=TransactionFinancial(
            gross_cents=fee,
            stripe_fee_cents=fees.stripe_fee_cents if fee else 0,
            net_after_stripe_cents=fees.net_after_stripe_cents if fee else 0,
            platform_fee_percent=fees.platform_fee_percent,
            platform_fee_cents=fees.platform_fee_cents if fee else 0,
            seller_net_cents=fees.seller_net_cents if fee else 0,
        ),
        donate=DonatePointer(handling_fee_cents=fee),
        status="pending",
    )

    # Always JWT path for now — PayPal handling-fee branch is a follow-up
    # that will wrap this in paypal_client.create_order() and only email
    # after capture. For Wave 2 we email the donor accept/deny links
    # and surface the handling fee as display-only metadata on the tx.
    token, jti = action_tokens.mint(
        tx_id=tx.id, role="donor", decision_choices=("accept", "deny"),
        expires_hours=24 * 7,
    )
    tx.donate.action_token_jti = jti
    doc = tx.model_dump()
    await repos.insert(db.transactions, doc)

    # Reuse swap_request template under the hood — same shape (item
    # card + accept/deny buttons). Donor = lister, recipient = swapper.
    try:
        donor = await _load_user(db, listing["seller_id"]) or {}
        recipient = user
        listing_item = await _load_listing_item(db, listing)
        recipient_card = {
            "title": (
                f"Claim from {recipient.get('display_name') or recipient.get('first_name') or 'a community member'}"
            ),
            "brand": (recipient.get("address") or {}).get("city"),
        }
        if donor.get("email"):
            await es.swap_request(
                to=donor["email"],
                lister=donor, swapper=recipient,
                listing_item=listing_item, offered_item=recipient_card,
                accept_url=_action_url(token, "accept"),
                deny_url=_action_url(token, "deny"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("donation email dispatch failed for %s: %s", tx.id, exc)

    return doc


# -----------------------------------------------------------------
# Wave 2 — Public action endpoint hit from email links
# -----------------------------------------------------------------
@router.get("/action")
async def transaction_action(
    token: str = Query(...),
    decision: str = Query(..., regex="^(accept|deny)$"),
) -> RedirectResponse:
    db = get_db()
    payload = action_tokens.verify(token, expected_decision=decision)
    tx_id = payload.get("sub")
    presented_jti = payload.get("jti")

    tx = await repos.find_one(db.transactions, {"id": tx_id}) if tx_id else None
    if not tx:
        return _landing_redirect(tx_id or "unknown", "invalid")

    kind = tx.get("kind", "buy")
    if kind not in ("swap", "donate"):
        return _landing_redirect(tx_id, "invalid")

    nested = tx.get(kind) or {}
    expected_jti = nested.get("action_token_jti")
    used = nested.get("action_token_used")

    if not expected_jti or expected_jti != presented_jti:
        return _landing_redirect(tx_id, "invalid")
    if used:
        # Idempotent: figure out which decision we already recorded and
        # bounce them to the same landing state instead of re-applying.
        if nested.get("accepted_at"):
            return _landing_redirect(tx_id, "accepted")
        if nested.get("denied_at"):
            return _landing_redirect(tx_id, "denied")
        return _landing_redirect(tx_id, "invalid")

    now = _now_iso()
    if decision == "accept":
        update = {
            f"{kind}.accepted_at": now,
            f"{kind}.action_token_used": True,
            "status": "accepted",
            "updated_at": now,
        }
    else:
        update = {
            f"{kind}.denied_at": now,
            f"{kind}.action_token_used": True,
            "status": "denied",
            "updated_at": now,
        }
    await db.transactions.update_one({"id": tx_id}, {"$set": update})

    if decision == "accept":
        await db.listings.update_one(
            {"id": tx["listing_id"]},
            {"$set": {"status": "reserved", "updated_at": now}},
        )

    # Fire follow-up emails — best-effort.
    try:
        listing = await db.listings.find_one(
            {"id": tx["listing_id"]}, {"_id": 0}
        ) or {}
        listing_item = await _load_listing_item(db, listing)
        lister = await _load_user(db, tx["seller_id"]) or {}
        counterpart = await _load_user(db, tx["buyer_id"]) or {}

        if kind == "swap":
            offered = await db.closet_items.find_one(
                {"id": (tx.get("swap") or {}).get("offered_item_id")},
                {
                    "_id": 0, "title": 1, "brand": 1,
                    "thumbnail_data_url": 1,
                    "segmented_image_url": 1,
                    "original_image_url": 1,
                },
            ) or {}
            offered_card = {
                "title": offered.get("title"),
                "brand": offered.get("brand"),
                "thumbnail_data_url": (
                    offered.get("thumbnail_data_url")
                    or offered.get("segmented_image_url")
                    or offered.get("original_image_url")
                ),
            }
            if decision == "accept":
                confirm_url = f"{_APP_URL}/transactions/{tx_id}/landing?status=accepted"
                if lister.get("email"):
                    await es.swap_success(
                        to=lister["email"],
                        recipient=lister, counterpart=counterpart,
                        recipient_item=listing_item,
                        counterpart_item=offered_card,
                        confirm_url=confirm_url, role="lister",
                    )
                if counterpart.get("email"):
                    await es.swap_success(
                        to=counterpart["email"],
                        recipient=counterpart, counterpart=lister,
                        recipient_item=offered_card,
                        counterpart_item=listing_item,
                        confirm_url=confirm_url, role="swapper",
                    )
            else:
                if counterpart.get("email"):
                    await es.swap_denied(
                        to=counterpart["email"],
                        swapper=counterpart, lister=lister,
                        listing_item=listing_item,
                        offered_item=offered_card,
                    )
        else:  # donate
            if decision == "accept":
                recipients = [e for e in (
                    lister.get("email"), counterpart.get("email"),
                ) if e]
                if recipients:
                    await es.donation_both(
                        to=recipients,
                        donor=lister, recipient=counterpart,
                        item=listing_item,
                    )
            else:
                if counterpart.get("email"):
                    await es.swap_denied(
                        to=counterpart["email"],
                        swapper=counterpart, lister=lister,
                        listing_item=listing_item, offered_item={
                            "title": "your donation request",
                        },
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("post-action email dispatch failed for %s: %s", tx_id, exc)

    return _landing_redirect(tx_id, "accepted" if decision == "accept" else "denied")


# -----------------------------------------------------------------
# Wave 2 — Confirm receipt (auth'd; both parties ship + confirm)
# -----------------------------------------------------------------
@router.post("/{tx_id}/confirm-receipt")
async def confirm_receipt(
    tx_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    tx = await repos.find_one(db.transactions, {"id": tx_id})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if user["id"] not in (tx.get("buyer_id"), tx.get("seller_id")):
        raise HTTPException(403, "Not your transaction")
    kind = tx.get("kind")
    if kind not in ("swap", "donate"):
        raise HTTPException(400, "Receipts only apply to swap/donate flows")
    if tx.get("status") not in ("accepted", "shipped"):
        raise HTTPException(
            409,
            "This transaction is not in a confirmable state. Both parties must accept first.",
        )

    now = _now_iso()
    role = "lister" if user["id"] == tx["seller_id"] else "swapper"
    field = f"{kind}.{role}_received_at"
    await db.transactions.update_one({"id": tx_id}, {"$set": {field: now, "updated_at": now}})

    tx2 = await repos.find_one(db.transactions, {"id": tx_id}) or {}
    nested = tx2.get(kind) or {}
    if kind == "swap":
        complete = bool(nested.get("lister_received_at") and nested.get("swapper_received_at"))
    else:
        # Donations require only the recipient to confirm receipt.
        complete = bool(nested.get("swapper_received_at"))

    if complete:
        await db.transactions.update_one(
            {"id": tx_id},
            {"$set": {
                f"{kind}.completed_at": now,
                "status": "completed",
                "updated_at": now,
            }},
        )
        await db.listings.update_one(
            {"id": tx2["listing_id"]},
            {"$set": {"status": "sold" if kind == "donate" else "removed",
                      "updated_at": now}},
        )
        if kind == "swap":
            try:
                listing = await db.listings.find_one(
                    {"id": tx2["listing_id"]}, {"_id": 0, "closet_item_id": 1}
                ) or {}
                lister_item_id = listing.get("closet_item_id")
                swapper_item_id = (tx2.get("swap") or {}).get("offered_item_id")
                if lister_item_id:
                    await db.closet_items.update_one(
                        {"id": lister_item_id},
                        {"$set": {"user_id": tx2["buyer_id"], "updated_at": now}},
                    )
                if swapper_item_id:
                    await db.closet_items.update_one(
                        {"id": swapper_item_id},
                        {"$set": {"user_id": tx2["seller_id"], "updated_at": now}},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("swap closet ownership flip failed for %s: %s", tx_id, exc)

    return await repos.find_one(db.transactions, {"id": tx_id}) or {}


# -----------------------------------------------------------------
# Reads (existing — preserved)
# -----------------------------------------------------------------
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


# Public summary used by the email landing page. Returns only a minimal
# projection (no buyer/seller IDs, no tokens) so anyone holding a tx_id
# from an email link can render status + listing summary without auth.
# NOTE: declared BEFORE ``/{tx_id}`` so FastAPI matches the specific
# sub-path instead of capturing "landing-summary" as an id.
@router.get("/{tx_id}/landing-summary")
async def get_transaction_landing(tx_id: str) -> dict[str, Any]:
    db = get_db()
    tx = await db.transactions.find_one(
        {"id": tx_id},
        {
            "_id": 0, "id": 1, "kind": 1, "status": 1,
            "listing_id": 1, "currency": 1, "created_at": 1,
            "swap.accepted_at": 1, "swap.denied_at": 1,
            "donate.accepted_at": 1, "donate.denied_at": 1,
        },
    )
    if not tx:
        raise HTTPException(404, "Transaction not found")
    listing = await db.listings.find_one(
        {"id": tx["listing_id"]},
        {
            "_id": 0, "id": 1, "title": 1, "description": 1,
            "size": 1, "condition": 1, "category": 1,
            "images": 1, "mode": 1, "status": 1,
            "financial_metadata": 1,
        },
    ) or {}
    return {"transaction": tx, "listing": listing}


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


# Re-export PayPalPointer import for any existing consumers of this
# module that might have been reaching in via package-level scan.
__all__ = ["router", "PayPalPointer"]
