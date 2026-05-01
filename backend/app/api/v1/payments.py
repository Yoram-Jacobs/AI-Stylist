"""Phase 4P — PayPal orders, credits, marketplace buy, payouts, webhooks.

Everything PayPal-related lives here:

- /paypal/config           public SDK config for the frontend
- /paypal/webhook          inbound webhook (signature verified unless dev flag)
- /credits/balance         per-currency ad credit balance
- /credits/history         top-up history
- /credits/topup           create PayPal order for a credit pack
- /credits/topup/.../capture  capture order + credit the balance
- /listings/{id}/buy       create PayPal order for a marketplace listing
- /listings/{id}/buy/capture  capture + Transaction + schedule seller payout
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.db.database import get_db
from app.models.schemas import (
    CreditTopup,
    PayPalPointer,
    Transaction,
    TransactionFinancial,
    UserCredits,
)
from app.services import paypal_client
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

paypal_router = APIRouter(prefix="/paypal", tags=["paypal"])
credits_router = APIRouter(prefix="/credits", tags=["credits"])
# marketplace_buy routes are attached under the existing listings prefix
buy_router = APIRouter(prefix="/listings", tags=["listings"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_configured() -> None:
    if not paypal_client.is_configured():
        raise HTTPException(
            503,
            {
                "code": "paypal_not_configured",
                "message": (
                    "PayPal is not configured on this environment. Add "
                    "PAYPAL_SANDBOX_CLIENT_ID + PAYPAL_SANDBOX_SECRET "
                    "to /app/backend/.env and restart."
                ),
            },
        )


def _platform_fee_math(gross_cents: int) -> TransactionFinancial:
    """Reuse the Phase-2 fee math but parameterise with PayPal percent.

    Policy: platform fee applied AFTER processing fee (keeps sellers net
    stable even as processors tweak their rates). PayPal's standard
    rate for US transactions is 3.49% + $0.49; we use that as a
    placeholder and keep the same `platform_fee_applied_after` key.
    """
    processing_pct = 3.49
    processing_fixed = 49
    processing_fee = round(gross_cents * (processing_pct / 100.0)) + processing_fixed
    net_after_processing = max(0, gross_cents - processing_fee)
    platform_pct = settings.PAYPAL_PLATFORM_FEE_PERCENT
    platform_fee = round(net_after_processing * (platform_pct / 100.0))
    seller_net = max(0, net_after_processing - platform_fee)
    return TransactionFinancial(
        gross_cents=gross_cents,
        stripe_fee_cents=processing_fee,  # repurposed field for processor fee
        net_after_stripe_cents=net_after_processing,
        platform_fee_percent=platform_pct,
        platform_fee_cents=platform_fee,
        seller_net_cents=seller_net,
        platform_fee_applied_after="stripe_processing_fee",
    )


# ------------------------------------------------------------------
# /paypal/config — public (unauthed) so the SDK can load early
# ------------------------------------------------------------------
@paypal_router.get("/config")
async def paypal_config() -> dict[str, Any]:
    return paypal_client.public_config()


# ------------------------------------------------------------------
# /paypal/webhook — generic inbound
# ------------------------------------------------------------------
@paypal_router.post("/webhook")
async def paypal_webhook(req: Request) -> dict[str, Any]:
    body = await req.json()
    headers = {k.lower(): v for k, v in req.headers.items()}
    event_id = body.get("id")
    event_type = body.get("event_type", "")
    # Idempotency: skip duplicates silently.
    db = get_db()
    if event_id:
        exists = await db.paypal_events.find_one({"id": event_id}, {"_id": 0, "id": 1})
        if exists:
            return {"ok": True, "duplicate": True}

    verified = await paypal_client.verify_webhook_signature(
        headers=headers, body=body
    )
    doc = {
        "id": event_id or f"evt_{uuid.uuid4()}",
        "event_type": event_type,
        "resource_type": body.get("resource_type"),
        "received_at": _now_iso(),
        "verified": verified,
        "payload": body,
    }
    await db.paypal_events.insert_one(doc)
    if not verified:
        logger.warning("PayPal webhook NOT verified: %s", event_type)
        return {"ok": False, "reason": "signature_not_verified"}

    # Route supported events.
    try:
        if event_type in (
            "PAYMENT.CAPTURE.COMPLETED",
            "PAYMENT.CAPTURE.DENIED",
            "PAYMENT.CAPTURE.REFUNDED",
        ):
            await _handle_capture_event(body)
        elif event_type in (
            "PAYMENTS.PAYOUTS-ITEM.SUCCEEDED",
            "PAYMENTS.PAYOUTS-ITEM.FAILED",
            "PAYMENTS.PAYOUTS-ITEM.BLOCKED",
        ):
            await _handle_payout_item_event(body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Webhook handler error: %s", exc)
    return {"ok": True}


async def _handle_capture_event(evt: dict[str, Any]) -> None:
    resource = evt.get("resource") or {}
    capture_id = resource.get("id")
    supplementary = resource.get("supplementary_data") or {}
    related = supplementary.get("related_ids") or {}
    order_id = related.get("order_id")
    status = resource.get("status")
    db = get_db()
    if order_id:
        await db.transactions.update_one(
            {"paypal.order_id": order_id},
            {
                "$set": {
                    "paypal.capture_id": capture_id,
                    "paypal.status": status,
                    "updated_at": _now_iso(),
                }
            },
        )


async def _handle_payout_item_event(evt: dict[str, Any]) -> None:
    resource = evt.get("resource") or {}
    payout_item_id = resource.get("payout_item_id")
    transaction_status = resource.get("transaction_status")
    db = get_db()
    if payout_item_id:
        await db.transactions.update_one(
            {"paypal.payout_item_id": payout_item_id},
            {
                "$set": {
                    "paypal.payout_status": transaction_status,
                    "updated_at": _now_iso(),
                }
            },
        )


# ------------------------------------------------------------------
# Credits
# ------------------------------------------------------------------
_PACK_PRICES = {"10": 1000, "25": 2500, "50": 5000}


class TopupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack: Literal["10", "25", "50", "custom"]
    custom_amount_cents: int | None = Field(default=None, ge=0, le=100000)
    currency: str = "USD"


async def _get_or_create_credits(
    db, user_id: str, currency: str
) -> dict[str, Any]:
    currency = currency.upper()
    doc = await db.user_credits.find_one(
        {"user_id": user_id, "currency": currency}, {"_id": 0}
    )
    if doc:
        return doc
    fresh = UserCredits(user_id=user_id, currency=currency).model_dump()
    await db.user_credits.insert_one(fresh)
    return fresh


@credits_router.get("/balance")
async def get_balance(
    currency: str = "USD", user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    doc = await _get_or_create_credits(db, user["id"], currency)
    return {
        "currency": doc["currency"],
        "balance_cents": int(doc.get("balance_cents", 0)),
    }


@credits_router.get("/balances")
async def list_balances(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    db = get_db()
    cursor = db.user_credits.find({"user_id": user["id"]}, {"_id": 0})
    items = [
        {
            "currency": d["currency"],
            "balance_cents": int(d.get("balance_cents", 0)),
        }
        async for d in cursor
    ]
    return {"items": items}


@credits_router.get("/history")
async def topup_history(
    limit: int = 30, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    cursor = (
        db.credit_topups.find({"user_id": user["id"]}, {"_id": 0})
        .sort("created_at", -1)
        .limit(max(1, min(200, limit)))
    )
    items = [d async for d in cursor]
    return {"items": items, "total": len(items)}


@credits_router.post("/topup")
async def create_topup(
    payload: TopupIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    _require_configured()
    currency = payload.currency.upper()
    if payload.pack == "custom":
        amount_cents = int(payload.custom_amount_cents or 0)
        if amount_cents < 100:
            raise HTTPException(
                400,
                {
                    "code": "amount_too_small",
                    "message": "Custom top-up amount must be at least 1.00.",
                },
            )
    else:
        amount_cents = _PACK_PRICES[payload.pack]
    if amount_cents < 100:
        raise HTTPException(400, "Amount must be at least 1.00")

    db = get_db()
    topup = CreditTopup(
        user_id=user["id"],
        amount_cents=amount_cents,
        currency=currency,
        pack=payload.pack,
    )
    doc = topup.model_dump()

    try:
        order = await paypal_client.create_order(
            amount_cents=amount_cents,
            currency=currency,
            reference_id=f"topup:{topup.id}",
            description=f"DressApp ad credit top-up ({currency} {amount_cents/100:.2f})",
            custom_id=topup.id,
        )
    except paypal_client.PayPalError as exc:
        raise HTTPException(502, {"paypal_error": str(exc.body)}) from exc
    doc["paypal_order_id"] = order["id"]
    await db.credit_topups.insert_one(doc)
    return {"topup_id": topup.id, "order_id": order["id"], "amount_cents": amount_cents, "currency": currency}


@credits_router.post("/topup/{topup_id}/capture")
async def capture_topup(
    topup_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    _require_configured()
    db = get_db()
    topup = await db.credit_topups.find_one(
        {"id": topup_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not topup:
        raise HTTPException(404, "Topup not found")
    if topup.get("status") == "captured":
        return {"ok": True, "already_captured": True, "topup": topup}
    order_id = topup.get("paypal_order_id")
    if not order_id:
        raise HTTPException(400, "Topup has no PayPal order id")
    try:
        captured = await paypal_client.capture_order(order_id)
    except paypal_client.PayPalError as exc:
        await db.credit_topups.update_one(
            {"id": topup_id}, {"$set": {"status": "failed", "updated_at": _now_iso()}}
        )
        raise HTTPException(502, {"paypal_error": str(exc.body)}) from exc

    capture_status = (
        (captured.get("purchase_units") or [{}])[0]
        .get("payments", {})
        .get("captures", [{}])[0]
        .get("status", "COMPLETED")
    )
    capture_id = (
        (captured.get("purchase_units") or [{}])[0]
        .get("payments", {})
        .get("captures", [{}])[0]
        .get("id")
    )
    payer_email = (captured.get("payer") or {}).get("email_address")

    new_status = "captured" if capture_status == "COMPLETED" else "pending"
    await db.credit_topups.update_one(
        {"id": topup_id},
        {
            "$set": {
                "status": new_status,
                "paypal_capture_id": capture_id,
                "captured_at": _now_iso(),
                "payer_email": payer_email,
                "updated_at": _now_iso(),
            }
        },
    )

    if new_status == "captured":
        # Credit balance atomically.
        await db.user_credits.update_one(
            {"user_id": user["id"], "currency": topup["currency"]},
            {
                "$inc": {"balance_cents": int(topup["amount_cents"])},
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "user_id": user["id"],
                    "currency": topup["currency"],
                    "created_at": _now_iso(),
                },
                "$set": {"updated_at": _now_iso()},
            },
            upsert=True,
        )

    final = await db.credit_topups.find_one({"id": topup_id}, {"_id": 0})
    balance = await _get_or_create_credits(db, user["id"], topup["currency"])
    return {
        "ok": True,
        "topup": final,
        "balance": {
            "currency": balance["currency"],
            "balance_cents": balance.get("balance_cents", 0),
        },
    }


# ------------------------------------------------------------------
# Marketplace buy
# ------------------------------------------------------------------
@buy_router.post("/{listing_id}/buy")
async def listing_buy_create(
    listing_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    _require_configured()
    db = get_db()
    listing = await db.listings.find_one({"id": listing_id}, {"_id": 0})
    if not listing:
        raise HTTPException(404, "Listing not found")
    if listing["seller_id"] == user["id"]:
        raise HTTPException(400, "Cannot buy your own listing")
    if listing.get("status") != "active":
        raise HTTPException(400, "Listing is not active")

    price_cents = int(listing["financial_metadata"]["list_price_cents"])
    currency = listing["financial_metadata"].get("currency", "USD").upper()
    try:
        order = await paypal_client.create_order(
            amount_cents=price_cents,
            currency=currency,
            reference_id=f"listing:{listing_id}",
            description=f"{listing.get('title','DressApp item')}"[:127],
            custom_id=listing_id,
        )
    except paypal_client.PayPalError as exc:
        raise HTTPException(502, {"paypal_error": str(exc.body)}) from exc

    # Create pending transaction tied to the order
    financial = _platform_fee_math(price_cents)
    tx = Transaction(
        listing_id=listing_id,
        buyer_id=user["id"],
        seller_id=listing["seller_id"],
        currency=currency,
        financial=financial,
        paypal=PayPalPointer(order_id=order["id"]),
        status="pending",
    )
    tx_doc = tx.model_dump()
    await db.transactions.insert_one(tx_doc)
    return {
        "order_id": order["id"],
        "transaction_id": tx.id,
        "amount_cents": price_cents,
        "currency": currency,
    }


@buy_router.post("/{listing_id}/buy/capture")
async def listing_buy_capture(
    listing_id: str,
    order_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _require_configured()
    db = get_db()
    tx = await db.transactions.find_one(
        {"paypal.order_id": order_id, "listing_id": listing_id, "buyer_id": user["id"]},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(404, "Transaction not found for that order")
    if tx.get("status") == "paid":
        return {"ok": True, "already_captured": True, "transaction": tx}

    try:
        captured = await paypal_client.capture_order(order_id)
    except paypal_client.PayPalError as exc:
        await db.transactions.update_one(
            {"id": tx["id"]},
            {
                "$set": {
                    "status": "failed",
                    "paypal.status": "DENIED",
                    "updated_at": _now_iso(),
                }
            },
        )
        raise HTTPException(502, {"paypal_error": str(exc.body)}) from exc

    capture = (
        (captured.get("purchase_units") or [{}])[0]
        .get("payments", {})
        .get("captures", [{}])[0]
    )
    payer = captured.get("payer") or {}
    await db.transactions.update_one(
        {"id": tx["id"]},
        {
            "$set": {
                "status": "paid",
                "paid_at": _now_iso(),
                "paypal.capture_id": capture.get("id"),
                "paypal.status": capture.get("status", "COMPLETED"),
                "paypal.payer_id": payer.get("payer_id"),
                "paypal.payer_email": payer.get("email_address"),
                "paypal.captured_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        },
    )
    # Mark listing sold
    await db.listings.update_one(
        {"id": listing_id},
        {"$set": {"status": "sold", "updated_at": _now_iso()}},
    )

    # Try to schedule seller payout. If the seller has no PayPal email, we
    # record the intent and leave it to admin to reconcile.
    seller = await db.users.find_one(
        {"id": tx["seller_id"]}, {"_id": 0, "paypal_receiver_email": 1}
    )
    seller_email = (seller or {}).get("paypal_receiver_email")
    seller_net = int(tx["financial"]["seller_net_cents"])
    if seller_email and seller_net > 0:
        sender_batch_id = f"payout_{tx['id']}"[:30]
        try:
            payout = await paypal_client.create_payout(
                sender_batch_id=sender_batch_id,
                receiver_email=seller_email,
                amount_cents=seller_net,
                currency=tx["currency"],
                note=f"DressApp payout for listing {listing_id[:8]}",
                sender_item_id=tx["id"][:30],
            )
            batch = (payout.get("batch_header") or {}).get("payout_batch_id")
            await db.transactions.update_one(
                {"id": tx["id"]},
                {
                    "$set": {
                        "paypal.payout_batch_id": batch,
                        "paypal.payout_item_id": tx["id"][:30],
                        "paypal.payout_status": "PENDING",
                        "updated_at": _now_iso(),
                    }
                },
            )
        except paypal_client.PayPalError as exc:
            logger.warning("Payout failed for %s: %s", tx["id"], exc.body)
            await db.transactions.update_one(
                {"id": tx["id"]},
                {"$set": {"paypal.payout_status": "FAILED", "updated_at": _now_iso()}},
            )

    final = await db.transactions.find_one({"id": tx["id"]}, {"_id": 0})

    # Marketplace celebration emails — fire AFTER the transaction is
    # safely persisted as paid. Best-effort: a failure here must
    # never roll back a successful capture or surface a 500 to the
    # buyer, so we wrap the whole block.
    try:
        from app.services import email_service as es

        seller_full = await db.users.find_one({"id": tx["seller_id"]}, {"_id": 0})
        buyer_full = await db.users.find_one({"id": tx["buyer_id"]}, {"_id": 0})
        listing_doc = await db.listings.find_one({"id": listing_id}, {"_id": 0})
        item_doc: dict[str, Any] = {}
        if listing_doc and listing_doc.get("closet_item_id"):
            item_doc = (
                await db.closet_items.find_one(
                    {"id": listing_doc["closet_item_id"]},
                    {
                        "_id": 0,
                        "title": 1, "brand": 1,
                        "thumbnail_data_url": 1,
                    },
                )
                or {}
            )
        # Fall back to listing fields if we couldn't load the closet item
        item_doc.setdefault("title", (listing_doc or {}).get("title"))
        if (listing_doc or {}).get("images"):
            item_doc.setdefault("thumbnail_data_url", listing_doc["images"][0])

        gross = int(tx["financial"]["gross_cents"])
        net = int(tx["financial"]["seller_net_cents"])
        currency = tx.get("currency", "USD")

        if seller_full and seller_full.get("email"):
            await es.sale_seller(
                to=seller_full["email"],
                seller=seller_full, buyer=buyer_full or {}, item=item_doc,
                gross_cents=gross, seller_net_cents=net, currency=currency,
            )
        if buyer_full and buyer_full.get("email"):
            await es.sale_buyer(
                to=buyer_full["email"],
                buyer=buyer_full, seller=seller_full or {}, item=item_doc,
                gross_cents=gross, currency=currency,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("post-sale email dispatch failed for %s: %s", tx["id"], exc)

    return {"ok": True, "transaction": final}
