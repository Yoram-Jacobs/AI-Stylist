"""Admin Dashboard API \u2014 control + observability surface for DressApp.

All endpoints require ``roles=['admin']`` (see ``app.services.auth.require_admin``).

Sections:
* ``/admin/overview``    \u2014 single-call summary card data
* ``/admin/users``       \u2014 paginated users + recent activity
* ``/admin/listings``    \u2014 paginated listings with status filter + moderation actions
* ``/admin/transactions`` \u2014 ledger view with revenue aggregation
* ``/admin/providers``   \u2014 in-memory provider activity (latency, error rate, last call)
* ``/admin/trend-scout`` \u2014 history + manual force-run
* ``/admin/llm-usage``   \u2014 best-effort Emergent LLM key usage probe
* ``/admin/system``      \u2014 service-mode toggles (read + flip in-memory only for now)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.db.database import get_db
from app.services import provider_activity
from app.services.auth import require_admin
from app.services.trend_scout import latest_trend_cards, run_trend_scout

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# -------------------- overview --------------------
@router.get("/overview")
async def overview(_: dict = Depends(require_admin)) -> dict[str, Any]:
    db = get_db()
    now = datetime.now(timezone.utc)
    last_24h = (now - timedelta(hours=24)).isoformat()
    last_7d = (now - timedelta(days=7)).isoformat()

    users_total = await db.users.count_documents({})
    users_24h = await db.users.count_documents({"created_at": {"$gte": last_24h}})
    items_total = await db.closet_items.count_documents({})
    listings_active = await db.listings.count_documents({"status": "active"})
    listings_total = await db.listings.count_documents({})
    tx_total = await db.transactions.count_documents({})
    tx_paid = await db.transactions.count_documents({"status": "paid"})

    pipeline = [
        {"$match": {"status": "paid"}},
        {
            "$group": {
                "_id": None,
                "gross": {"$sum": "$financial.gross_cents"},
                "platform_fee": {"$sum": "$financial.platform_fee_cents"},
                "stripe_fee": {"$sum": "$financial.stripe_fee_cents"},
                "seller_net": {"$sum": "$financial.seller_net_cents"},
            }
        },
    ]
    revenue = {"gross": 0, "platform_fee": 0, "stripe_fee": 0, "seller_net": 0}
    async for row in db.transactions.aggregate(pipeline):
        revenue.update(
            {
                "gross": row.get("gross", 0),
                "platform_fee": row.get("platform_fee", 0),
                "stripe_fee": row.get("stripe_fee", 0),
                "seller_net": row.get("seller_net", 0),
            }
        )

    stylist_24h = await db.stylist_messages.count_documents(
        {"created_at": {"$gte": last_24h}}
    )
    stylist_7d = await db.stylist_messages.count_documents(
        {"created_at": {"$gte": last_7d}}
    )

    trend_cards = await latest_trend_cards(limit_per_bucket=1)

    return {
        "users": {"total": users_total, "new_24h": users_24h},
        "closet_items": {"total": items_total},
        "listings": {"total": listings_total, "active": listings_active},
        "transactions": {"total": tx_total, "paid": tx_paid},
        "revenue_cents": revenue,
        "stylist": {"messages_24h": stylist_24h, "messages_7d": stylist_7d},
        "trend_scout": {"latest": trend_cards, "count": len(trend_cards)},
        "providers": provider_activity.summary(),
        "generated_at": now.isoformat(),
    }


# -------------------- users --------------------
@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    q: str | None = Query(None),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {}
    if q:
        flt["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"display_name": {"$regex": q, "$options": "i"}},
        ]
    total = await db.users.count_documents(flt)
    items: list[dict[str, Any]] = []
    cursor = (
        db.users.find(flt, {"_id": 0, "password_hash": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    async for doc in cursor:
        # add lightweight per-user counts
        doc["closet_count"] = await db.closet_items.count_documents(
            {"user_id": doc["id"]}
        )
        doc["listing_count"] = await db.listings.count_documents(
            {"seller_id": doc["id"]}
        )
        doc["calendar_connected"] = bool(
            (doc.get("google_calendar_tokens") or {}).get("refresh_token")
        )
        # never leak the raw tokens object
        doc.pop("google_calendar_tokens", None)
        items.append(doc)
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/users/{user_id}/promote")
async def promote_user(
    user_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"id": user_id}, {"$addToSet": {"roles": "admin"}}
    )
    if not res.matched_count:
        raise HTTPException(404, "User not found")
    return {"status": "ok", "user_id": user_id, "added_role": "admin"}


@router.post("/users/{user_id}/demote")
async def demote_user(
    user_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"id": user_id}, {"$pull": {"roles": "admin"}}
    )
    if not res.matched_count:
        raise HTTPException(404, "User not found")
    return {"status": "ok", "user_id": user_id, "removed_role": "admin"}


# -------------------- listings --------------------
@router.get("/listings")
async def list_listings(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {}
    if status:
        flt["status"] = status
    total = await db.listings.count_documents(flt)
    cursor = (
        db.listings.find(flt, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/listings/{listing_id}/status")
async def set_listing_status(
    listing_id: str,
    status: str = Query(..., regex="^(active|paused|removed|sold)$"),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    res = await db.listings.update_one(
        {"id": listing_id},
        {
            "$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if not res.matched_count:
        raise HTTPException(404, "Listing not found")
    return {"status": "ok", "listing_id": listing_id, "new_status": status}


# -------------------- transactions --------------------
@router.get("/transactions")
async def list_transactions(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {}
    if status:
        flt["status"] = status
    total = await db.transactions.count_documents(flt)
    cursor = (
        db.transactions.find(flt, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


# -------------------- providers --------------------
@router.get("/providers")
async def providers(_: dict = Depends(require_admin)) -> dict[str, Any]:
    return {"summary": provider_activity.summary()}


@router.get("/providers/{provider}/calls")
async def provider_calls(
    provider: str,
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    snap = provider_activity.snapshot(provider).get(provider, [])
    return {"provider": provider, "calls": snap[-limit:], "count": len(snap)}


# -------------------- trend-scout --------------------
@router.get("/trend-scout")
async def trend_scout_history(
    limit: int = Query(30, ge=1, le=200),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    cursor = (
        db.trend_reports.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "count": len(items)}


@router.post("/trend-scout/run")
async def trend_scout_run(
    force: bool = Query(default=True),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    return await run_trend_scout(force=force)


# -------------------- LLM key usage --------------------
@router.get("/llm-usage")
async def llm_usage(_: dict = Depends(require_admin)) -> dict[str, Any]:
    """Best-effort probe of the Emergent universal-key usage endpoint.

    The Emergent proxy exposes a usage endpoint; if it ever changes we just
    return an informational stub instead of failing the dashboard.
    """
    if not settings.EMERGENT_LLM_KEY:
        return {"available": False, "reason": "EMERGENT_LLM_KEY not set"}
    headers = {"Authorization": f"Bearer {settings.EMERGENT_LLM_KEY}"}
    candidates = [
        "https://integrations.emergentagent.com/v1/usage",
        "https://emergent-llm.com/v1/usage",
    ]
    for url in candidates:
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                resp = await c.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return {"available": True, "source": url, "usage": data}
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM usage probe %s failed: %s", url, exc)
    return {
        "available": False,
        "reason": "No usage endpoint reachable; check Emergent dashboard.",
        "manage_url": "https://emergentagent.com/profile/universal-key",
    }


# -------------------- system / config view --------------------
@router.get("/system")
async def system_view(_: dict = Depends(require_admin)) -> dict[str, Any]:
    """Surface runtime configuration (redacted) so admins can see what's
    plugged in without SSH access. Never expose secrets.
    """

    def _has(v: Any) -> bool:
        return bool(v)

    return {
        "ai": {
            "stylist_provider": settings.DEFAULT_STYLIST_PROVIDER,
            "stylist_model": settings.DEFAULT_STYLIST_MODEL,
            "image_model": settings.HF_IMAGE_MODEL,
            "image_provider": settings.HF_IMAGE_PROVIDER,
            "segmentation_model": settings.HF_SAM_MODEL,
            "tts_model": settings.DEFAULT_TTS_MODEL,
            "whisper_model": settings.WHISPER_MODEL,
        },
        "keys_present": {
            "EMERGENT_LLM_KEY": _has(settings.EMERGENT_LLM_KEY),
            "HF_TOKEN": _has(settings.HF_TOKEN),
            "GROQ_API_KEY": _has(settings.GROQ_API_KEY),
            "DEEPGRAM_API_KEY": _has(settings.DEEPGRAM_API_KEY),
            "OPENWEATHER_API_KEY": _has(settings.OPENWEATHER_API_KEY),
            "GOOGLE_OAUTH_CLIENT_ID": _has(settings.GOOGLE_OAUTH_CLIENT_ID),
            "GOOGLE_OAUTH_CLIENT_SECRET": _has(settings.GOOGLE_OAUTH_CLIENT_SECRET),
        },
        "trend_scout": {
            "enabled": settings.TREND_SCOUT_ENABLED,
            "schedule_utc": settings.TREND_SCOUT_SCHEDULE_UTC,
        },
        "dev": {
            "allow_dev_bypass": settings.ALLOW_DEV_BYPASS,
        },
    }
