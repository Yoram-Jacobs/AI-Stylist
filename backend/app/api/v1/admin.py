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
import os
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


# -------------------- eyes provider toggle --------------------
# Phase O.3 — runtime override for the closet vision pipeline. Flips
# the model server between the self-hosted Gemma-4 E2B endpoint and the
# Gemini-2.5-Flash safety-net path without a backend restart. The
# override is persisted in ``config.{_id: 'eyes_provider'}`` and read
# through a 5-second cache (see ``app.services.eyes_override``).
@router.get("/eyes")
async def eyes_status(_: dict = Depends(require_admin)) -> dict[str, Any]:
    """Snapshot of the active Eyes provider + recent inference calls.

    Combines the persisted override (``config`` collection) with the
    most-recent ``garment-vision`` provider-activity entries so the
    Profile UI can show "Gemma — last call ok in 4.2 s" out of the
    box. No DB write happens here; safe to poll.
    """
    from app.services import eyes_override

    snap = await eyes_override.status()
    recent = provider_activity.snapshot("garment-vision").get("garment-vision", [])
    last_calls = recent[-5:]  # newest 5 in chronological order
    return {
        **snap,
        "recent_calls": last_calls,
        "last_call": last_calls[-1] if last_calls else None,
    }


@router.post("/eyes")
async def eyes_set_override(
    payload: dict[str, Any],
    user: dict = Depends(require_admin),
) -> dict[str, Any]:
    """Set or clear the Eyes provider override.

    Body::

        { "provider": "gemma" | "gemini" | null }

    A null / missing / empty ``provider`` clears the override and
    reverts the pod to the env-default. Any non-allowlisted value
    returns 400 — we deliberately don't silently coerce to keep the
    audit trail clean.
    """
    from app.services import eyes_override

    raw = payload.get("provider") if isinstance(payload, dict) else None
    by_email = (user.get("email") or "").lower() or None
    try:
        new_status = await eyes_override.set_override(raw, by_email=by_email)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return new_status


# -------------------- eyes diagnostics --------------------
# Phase O.4 — one-shot diagnostic probe for the Eyes pipeline. This
# is the "is my custom Gemma actually serving requests right now?"
# question answered in a single GET. It composites:
#   * The DB toggle resolution (override + env default + active value)
#   * The pod's vision-routing env vars (GARMENT_VISION_PROVIDER /
#     _MODEL, EYES_PROVIDER, EYES_GEMMA_SPACE_URL)
#   * A live HTTP HEAD/GET probe of the Gemma Space with latency
#     and a body preview so 503/HTML "Space is in error" pages are
#     visible without leaving the admin UI
#   * The most recent N garment-vision provider_activity entries so
#     callers can see whether real traffic is succeeding
#
# Wire this into the Developer panel later; for now ``curl`` is the
# expected consumer (per the user's request).
@router.get("/eyes/diagnostics")
async def eyes_diagnostics(
    _: dict = Depends(require_admin),
    probe_timeout: float = Query(default=5.0, ge=0.5, le=15.0),
) -> dict[str, Any]:
    """Return a one-shot snapshot of the Eyes pipeline's health.

    Shape::

        {
          "toggle":   { ... eyes_override.status() ... },
          "env":      { GARMENT_VISION_PROVIDER, GARMENT_VISION_MODEL,
                        EYES_PROVIDER, EYES_GEMMA_SPACE_URL,
                        gemini_chat_key_set, eyes_bearer_set },
          "resolved": { provider, model, would_use, fallback_path,
                        notes },
          "gemma_space": { url, status_code, ok, latency_ms,
                           body_preview, error },
          "recent_calls": [ ...last 10 garment-vision activity rows... ]
        }
    """
    from app.services import eyes_override

    toggle_snap = await eyes_override.status()
    active_provider = toggle_snap["active_provider"]

    env_block = {
        "GARMENT_VISION_PROVIDER": settings.GARMENT_VISION_PROVIDER,
        "GARMENT_VISION_MODEL": settings.GARMENT_VISION_MODEL,
        "EYES_PROVIDER": settings.EYES_PROVIDER,
        "EYES_GEMMA_SPACE_URL": settings.EYES_GEMMA_SPACE_URL or None,
        "EYES_GEMMA_TIMEOUT_S": settings.EYES_GEMMA_TIMEOUT_S,
        "gemini_chat_key_set": bool(settings.gemini_chat_key),
        # Eyes container bearer (shared secret with the self-hosted
        # service). ``EYES_HF_TOKEN`` has been removed from the auth
        # surface — see quarantine/2026-05-sabotage/READ_THIS_FIRST.md.
        "eyes_bearer_set": bool(settings.EYES_API_TOKEN),
    }

    # Resolved view — what would happen on the very next analyze() call?
    notes: list[str] = []
    fallback_path: str | None = None
    if active_provider == "gemma":
        if settings.EYES_GEMMA_SPACE_URL:
            would_use = "gemma"
            fallback_path = "gemini (on Gemma Space failure)"
        else:
            would_use = "gemini"
            notes.append(
                "Toggle is set to 'gemma' but EYES_GEMMA_SPACE_URL is not "
                "configured on this pod — every request will silently use "
                "the Gemini fallback."
            )
    else:
        would_use = "gemini"

    resolved_block = {
        "provider": would_use,
        "model": (
            settings.GARMENT_VISION_MODEL
            if would_use == "gemini"
            else "gemma-4-e2b-q4_k_m"
        ),
        "routing_source": toggle_snap["source"],  # "db" | "env"
        "fallback_path": fallback_path,
        "notes": notes,
    }
    # Live Gemma Space probe — GET /health with a tight timeout. We
    # don't POST /predict because that would consume Gemma capacity
    # on every diagnostics call and risk a token-quota hit. /health
    # is what the HF Space exposes for liveness.
    gemma_url = (settings.EYES_GEMMA_SPACE_URL or "").rstrip("/")
    space_block: dict[str, Any] = {
        "url": gemma_url or None,
        "status_code": None,
        "ok": False,
        "latency_ms": None,
        "body_preview": None,
        "error": None,
    }
    if gemma_url:
        import time as _t

        # Some HF Spaces don't expose /health — fall back to the root
        # gradio page on 404. Both responses are short.
        async def _probe(path: str) -> tuple[int, str, float]:
            t0 = _t.perf_counter()
            async with httpx.AsyncClient(timeout=probe_timeout) as cli:
                r = await cli.get(f"{gemma_url}{path}")
            return r.status_code, r.text[:300], (_t.perf_counter() - t0) * 1000

        try:
            code, body, latency = await _probe("/health")
            if code == 404:
                code, body, latency = await _probe("/")
            space_block["status_code"] = code
            space_block["ok"] = 200 <= code < 300
            space_block["latency_ms"] = int(latency)
            space_block["body_preview"] = body
        except Exception as exc:  # noqa: BLE001
            space_block["error"] = repr(exc)[:300]

    # Most-recent traffic — the source of truth for "is Gemma actually
    # answering, even if /health says ok?".
    recent_all = provider_activity.snapshot("garment-vision").get(
        "garment-vision", []
    )
    recent_calls = recent_all[-10:]

    return {
        "toggle": toggle_snap,
        "env": env_block,
        "resolved": resolved_block,
        "gemma_space": space_block,
        "recent_calls": recent_calls,
    }


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
    return an informational stub instead of failing the dashboard. When
    production has flipped to a direct Gemini key, the Emergent endpoint
    is irrelevant — we surface that explicitly.
    """
    if settings.has_native_gemini and not settings.EMERGENT_LLM_KEY:
        return {
            "available": False,
            "reason": "Production is using a direct GEMINI_API_KEY; Emergent "
            "usage is not applicable. Check usage at "
            "https://aistudio.google.com/apikey or in Google Cloud Console.",
            "backend": "google-direct",
        }
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
            "image_model": settings.GEMINI_IMAGE_MODEL,
            "image_provider": "google-nano-banana",
            "segmentation_model": settings.HF_SAM_MODEL,
            "tts_model": settings.DEFAULT_TTS_MODEL,
            "whisper_model": settings.WHISPER_MODEL,
        },
        "keys_present": {
            "EMERGENT_LLM_KEY": _has(settings.EMERGENT_LLM_KEY),
            "GEMINI_API_KEY": _has(settings.GEMINI_API_KEY),
            "GROQ_API_KEY": _has(settings.GROQ_API_KEY),
            "DEEPGRAM_API_KEY": _has(settings.DEEPGRAM_API_KEY),
            "OPENWEATHER_API_KEY": _has(settings.OPENWEATHER_API_KEY),
            "GOOGLE_OAUTH_CLIENT_ID": _has(settings.GOOGLE_OAUTH_CLIENT_ID),
            "GOOGLE_OAUTH_CLIENT_SECRET": _has(settings.GOOGLE_OAUTH_CLIENT_SECRET),
        },
        "llm_backend": (
            "google-direct" if settings.has_native_gemini else "emergent-proxy"
        ),
        "trend_scout": {
            "enabled": settings.TREND_SCOUT_ENABLED,
            "schedule_utc": settings.TREND_SCOUT_SCHEDULE_UTC,
        },
        "dev": {
            "allow_dev_bypass": settings.ALLOW_DEV_BYPASS,
        },
    }


# -------------------- professionals (Phase U) --------------------
@router.get("/professionals")
async def admin_list_professionals(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    include_hidden: bool = Query(True),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {"professional.is_professional": True}
    if not include_hidden:
        flt["professional.approval_status"] = {"$ne": "hidden"}
    total = await db.users.count_documents(flt)
    cursor = (
        db.users.find(flt, {"_id": 0, "password_hash": 0, "google_oauth": 0})
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/professionals/{user_id}/hide")
async def admin_hide_professional(
    user_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"id": user_id, "professional.is_professional": True},
        {
            "$set": {
                "professional.approval_status": "hidden",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if not res.matched_count:
        raise HTTPException(404, "Professional not found")
    return {"status": "ok", "user_id": user_id, "approval_status": "hidden"}


@router.post("/professionals/{user_id}/unhide")
async def admin_unhide_professional(
    user_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"id": user_id, "professional.is_professional": True},
        {
            "$set": {
                "professional.approval_status": "self",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if not res.matched_count:
        raise HTTPException(404, "Professional not found")
    return {"status": "ok", "user_id": user_id, "approval_status": "self"}


# -------------------- ad campaigns (Phase U) --------------------
@router.get("/promotions/campaigns")
async def admin_list_ad_campaigns(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    status: str | None = Query(None),
    _: dict = Depends(require_admin),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {}
    if status:
        flt["status"] = status
    total = await db.ad_campaigns.count_documents(flt)
    cursor = (
        db.ad_campaigns.find(flt, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/promotions/campaigns/{campaign_id}/disable")
async def admin_disable_campaign(
    campaign_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.ad_campaigns.update_one(
        {"id": campaign_id},
        {
            "$set": {
                "status": "disabled",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if not res.matched_count:
        raise HTTPException(404, "Campaign not found")
    return {"status": "ok", "id": campaign_id, "new_status": "disabled"}


@router.post("/promotions/campaigns/{campaign_id}/enable")
async def admin_enable_campaign(
    campaign_id: str, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    db = get_db()
    res = await db.ad_campaigns.update_one(
        {"id": campaign_id},
        {
            "$set": {
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if not res.matched_count:
        raise HTTPException(404, "Campaign not found")
    return {"status": "ok", "id": campaign_id, "new_status": "active"}
