"""Professionals Directory routes (Phase U).

Exposes a curated public listing of users who self-certify as fashion
professionals. Admin moderation (hide/unhide) lives under /admin/professionals.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.database import get_db

router = APIRouter(prefix="/professionals", tags=["professionals"])


def _public_view(user: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets and return the fields we expose in the directory."""
    prof = user.get("professional") or {}
    business = prof.get("business") or {}
    return {
        "id": user.get("id"),
        "display_name": user.get("display_name")
        or " ".join(
            [user.get("first_name") or "", user.get("last_name") or ""]
        ).strip()
        or "Fashion pro",
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "avatar_url": user.get("avatar_url"),
        "face_photo_url": user.get("face_photo_url"),
        "locale": user.get("locale"),
        "preferred_language": user.get("preferred_language"),
        "home_location": {
            "city": (user.get("home_location") or {}).get("city"),
            "country": (user.get("home_location") or {}).get("country"),
            "country_code": (user.get("home_location") or {}).get("country_code"),
            "region": (user.get("home_location") or {}).get("region"),
        },
        "address": {
            "city": (user.get("address") or {}).get("city"),
            "region": (user.get("address") or {}).get("region"),
            "country": (user.get("address") or {}).get("country"),
        },
        "professional": {
            "is_professional": prof.get("is_professional", True),
            "profession": prof.get("profession"),
            "business": {
                "name": business.get("name"),
                "phone": business.get("phone"),
                "email": business.get("email"),
                "website": business.get("website"),
                "address": business.get("address"),
                "description": business.get("description"),
            },
            "approval_status": prof.get("approval_status", "self"),
            "created_at": prof.get("created_at"),
        },
    }


@router.get("")
async def list_professionals(
    country: str | None = Query(None),
    region: str | None = Query(None),
    profession: str | None = Query(None),
    q: str | None = Query(None, description="Free-text search"),
    limit: int = Query(40, ge=1, le=100),
    skip: int = Query(0, ge=0),
) -> dict[str, Any]:
    db = get_db()
    flt: dict[str, Any] = {
        "professional.is_professional": True,
        "$or": [
            {"professional.approval_status": {"$ne": "hidden"}},
            {"professional.approval_status": {"$exists": False}},
        ],
    }
    if profession:
        flt["professional.profession"] = {"$regex": f"^{profession}$", "$options": "i"}
    if country:
        flt["$and"] = flt.get("$and", []) + [
            {
                "$or": [
                    {"home_location.country_code": {"$regex": f"^{country}$", "$options": "i"}},
                    {"home_location.country": {"$regex": f"^{country}$", "$options": "i"}},
                    {"address.country": {"$regex": f"^{country}$", "$options": "i"}},
                ]
            }
        ]
    if region:
        flt.setdefault("$and", []).append(
            {
                "$or": [
                    {"home_location.region": {"$regex": region, "$options": "i"}},
                    {"address.region": {"$regex": region, "$options": "i"}},
                    {"home_location.city": {"$regex": region, "$options": "i"}},
                    {"address.city": {"$regex": region, "$options": "i"}},
                ]
            }
        )
    if q:
        flt.setdefault("$and", []).append(
            {
                "$or": [
                    {"display_name": {"$regex": q, "$options": "i"}},
                    {"first_name": {"$regex": q, "$options": "i"}},
                    {"last_name": {"$regex": q, "$options": "i"}},
                    {"professional.business.name": {"$regex": q, "$options": "i"}},
                    {"professional.profession": {"$regex": q, "$options": "i"}},
                ]
            }
        )

    total = await db.users.count_documents(flt)
    cursor = (
        db.users.find(flt, {"_id": 0, "password_hash": 0, "google_oauth": 0})
        .sort([("professional.created_at", -1), ("created_at", -1)])
        .skip(skip)
        .limit(limit)
    )
    items = [_public_view(doc) async for doc in cursor]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{user_id}")
async def get_professional(user_id: str) -> dict[str, Any]:
    db = get_db()
    user = await db.users.find_one(
        {"id": user_id, "professional.is_professional": True},
        {"_id": 0, "password_hash": 0, "google_oauth": 0},
    )
    if not user or (user.get("professional") or {}).get("approval_status") == "hidden":
        raise HTTPException(404, "Professional not found")
    return _public_view(user)
