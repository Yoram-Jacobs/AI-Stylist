"""/api/v1 router hub."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, closet, listings, stylist, transactions, users

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(closet.router)
api_v1_router.include_router(listings.router)
api_v1_router.include_router(transactions.router)
api_v1_router.include_router(stylist.router)


@api_v1_router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
