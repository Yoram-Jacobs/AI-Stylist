"""Ad Campaigns (Phase U).

Facebook-inspired one-level ads:
- professionals own `ad_campaigns`
- auction-lite ticker selects region-matched, active, in-budget campaigns
  weighted by `bid_cents` * pacing factor
- tracking counters for impressions/clicks/spent (no real billing yet — the
  PayPlus wiring is deferred)
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.db.database import get_db
from app.models.schemas import AdCampaign, AdCreative
from app.services.auth import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ads", tags=["ads"])


# ----------------------------- models -----------------------------
class AdCreativeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = Field(min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=280)
    image_url: str | None = None
    cta_label: str | None = Field(default=None, max_length=40)
    cta_url: str | None = None


class CampaignCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    profession: str | None = None
    creative: AdCreativeIn
    daily_budget_cents: int = Field(default=0, ge=0)
    bid_cents: int = Field(default=0, ge=0)
    start_date: str | None = None
    end_date: str | None = None
    target_country: str | None = None
    target_region: str | None = None
    status: str = "draft"


class CampaignPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    profession: str | None = None
    creative: AdCreativeIn | None = None
    daily_budget_cents: int | None = Field(default=None, ge=0)
    bid_cents: int | None = Field(default=None, ge=0)
    start_date: str | None = None
    end_date: str | None = None
    target_country: str | None = None
    target_region: str | None = None
    status: str | None = None


# ----------------------------- helpers -----------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _strip_doc(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


# ----------------------------- CRUD -----------------------------
@router.post("/campaigns")
async def create_campaign(
    payload: CampaignCreateIn, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    prof = (user.get("professional") or {})
    if not prof.get("is_professional"):
        raise HTTPException(403, "Only professionals can create ad campaigns")
    db = get_db()
    campaign = AdCampaign(
        owner_id=user["id"],
        name=payload.name,
        profession=payload.profession or prof.get("profession"),
        creative=AdCreative(**payload.creative.model_dump()),
        daily_budget_cents=payload.daily_budget_cents,
        bid_cents=payload.bid_cents,
        start_date=payload.start_date,
        end_date=payload.end_date,
        target_country=payload.target_country,
        target_region=payload.target_region,
        status=payload.status if payload.status in {"draft", "active", "paused"} else "draft",
    )
    doc = campaign.model_dump()
    await db.ad_campaigns.insert_one(doc)
    return _strip_doc(doc)


@router.get("/campaigns")
async def list_my_campaigns(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    db = get_db()
    cursor = (
        db.ad_campaigns.find({"owner_id": user["id"]}, {"_id": 0})
        .sort("created_at", -1)
        .limit(200)
    )
    items = [doc async for doc in cursor]
    return {"items": items, "total": len(items)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    doc = await db.ad_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Campaign not found")
    if doc["owner_id"] != user["id"] and "admin" not in (user.get("roles") or []):
        raise HTTPException(403, "Not allowed")
    return doc


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: str,
    payload: CampaignPatchIn,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    db = get_db()
    existing = await db.ad_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Campaign not found")
    if existing["owner_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    patch = payload.model_dump(exclude_none=True)
    # Only permit owners to transition to these states (admin uses /admin/ads/...).
    if "status" in patch and patch["status"] not in {"draft", "active", "paused", "ended"}:
        patch.pop("status")
    if "creative" in patch:
        patch["creative"] = AdCreative(**patch["creative"]).model_dump()
    patch["updated_at"] = _now_iso()
    await db.ad_campaigns.update_one({"id": campaign_id}, {"$set": patch})
    doc = await db.ad_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return doc or {}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    db = get_db()
    existing = await db.ad_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Campaign not found")
    if existing["owner_id"] != user["id"]:
        raise HTTPException(403, "Not allowed")
    await db.ad_campaigns.delete_one({"id": campaign_id})
    return {"status": "ok", "id": campaign_id}


# ----------------------------- ticker (public) -----------------------------
def _eligible_filter(country: str | None, region: str | None) -> dict[str, Any]:
    today = _today_iso_date()
    flt: dict[str, Any] = {
        "status": "active",
        "$and": [
            {
                "$or": [
                    {"start_date": {"$exists": False}},
                    {"start_date": None},
                    {"start_date": {"$lte": today}},
                ]
            },
            {
                "$or": [
                    {"end_date": {"$exists": False}},
                    {"end_date": None},
                    {"end_date": {"$gte": today}},
                ]
            },
        ],
    }
    if country:
        flt["$and"].append(
            {
                "$or": [
                    {"target_country": None},
                    {"target_country": {"$exists": False}},
                    {"target_country": {"$regex": f"^{country}$", "$options": "i"}},
                ]
            }
        )
    if region:
        flt["$and"].append(
            {
                "$or": [
                    {"target_region": None},
                    {"target_region": {"$exists": False}},
                    {"target_region": {"$regex": region, "$options": "i"}},
                ]
            }
        )
    return flt


@router.get("/ticker")
async def ticker(
    country: str | None = Query(None),
    region: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    _: dict | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """Return region-matched ads using bid-weighted random selection.

    MVP selection strategy: eligible campaigns are weighted by
    `max(bid_cents, 1) * max(1, daily_budget_cents - spent_today)`. We then
    sample without replacement up to `limit` items. Keeps higher-bidders and
    budget-healthy campaigns at the top.
    """
    db = get_db()
    flt = _eligible_filter(country, region)
    candidates = [doc async for doc in db.ad_campaigns.find(flt, {"_id": 0}).limit(200)]
    if not candidates:
        return {"items": [], "country": country, "region": region}

    def weight(c: dict[str, Any]) -> float:
        bid = max(1, int(c.get("bid_cents") or 0))
        # crude pacing: if over daily_budget, halve weight but don't zero out
        spent = int(c.get("spent_cents") or 0)
        budget = int(c.get("daily_budget_cents") or 0)
        pacing = 1.0
        if budget > 0 and spent >= budget:
            pacing = 0.25
        return bid * pacing

    weights = [weight(c) for c in candidates]
    # bias-weighted sampling without replacement
    chosen: list[dict[str, Any]] = []
    pool = list(zip(candidates, weights))
    k = min(limit, len(pool))
    for _ in range(k):
        total = sum(w for _, w in pool) or 1.0
        r = random.random() * total
        acc = 0.0
        pick_idx = 0
        for i, (_c, w) in enumerate(pool):
            acc += w
            if acc >= r:
                pick_idx = i
                break
        chosen.append(pool[pick_idx][0])
        pool.pop(pick_idx)

    # Public view for ticker
    items = []
    for c in chosen:
        items.append(
            {
                "id": c["id"],
                "owner_id": c["owner_id"],
                "profession": c.get("profession"),
                "creative": c.get("creative") or {},
                "target_country": c.get("target_country"),
                "target_region": c.get("target_region"),
            }
        )
    return {"items": items, "country": country, "region": region}


# ----------------------------- tracking -----------------------------
@router.post("/impression/{campaign_id}")
async def track_impression(campaign_id: str) -> dict[str, Any]:
    db = get_db()
    # Treat impression as 1¢ virtual charge so spend-pacing has teeth for MVP.
    res = await db.ad_campaigns.update_one(
        {"id": campaign_id, "status": "active"},
        {"$inc": {"impressions": 1, "spent_cents": 1}, "$set": {"updated_at": _now_iso()}},
    )
    return {"ok": bool(res.matched_count)}


@router.post("/click/{campaign_id}")
async def track_click(campaign_id: str) -> dict[str, Any]:
    db = get_db()
    res = await db.ad_campaigns.update_one(
        {"id": campaign_id, "status": "active"},
        {"$inc": {"clicks": 1, "spent_cents": 5}, "$set": {"updated_at": _now_iso()}},
    )
    return {"ok": bool(res.matched_count)}
