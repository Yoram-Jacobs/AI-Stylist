"""MongoDB (Motor) client with idempotent index bootstrap."""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.DB_NAME]
    return _db


async def ensure_indexes() -> None:
    """Create every index DressApp expects. Safe to call at every startup."""
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("stripe_account_id", sparse=True)

    await db.closet_items.create_index(
        [("user_id", 1), ("source", 1), ("category", 1)]
    )
    await db.closet_items.create_index(
        [("title", "text"), ("brand", "text"), ("tags", "text")]
    )

    await db.listings.create_index([("source", 1), ("status", 1), ("category", 1)])
    await db.listings.create_index([("seller_id", 1), ("status", 1)])
    await db.listings.create_index([("location", "2dsphere")], sparse=True)

    await db.transactions.create_index([("buyer_id", 1), ("created_at", -1)])
    await db.transactions.create_index([("seller_id", 1), ("created_at", -1)])
    # Partial-filter unique index: only enforce uniqueness when the Stripe
    # checkout session id is actually a non-empty string. This avoids the
    # classic "duplicate key on null" problem that breaks pre-payment writes.
    try:
        await db.transactions.drop_index("stripe.checkout_session_id_1")
    except Exception:  # noqa: BLE001
        pass
    await db.transactions.create_index(
        [("stripe.checkout_session_id", 1)],
        unique=True,
        partialFilterExpression={"stripe.checkout_session_id": {"$type": "string"}},
        name="stripe_checkout_session_id_unique_partial",
    )

    # Multi-session: one user can have many conversation threads, so we
    # index user_id non-uniquely alongside last_active_at for the sidebar
    # list. The legacy unique index (if present) is dropped on boot.
    try:
        await db.stylist_sessions.drop_index("user_id_1")
    except Exception:  # noqa: BLE001
        # Index may not exist (fresh DB) — safe to ignore.
        pass
    await db.stylist_sessions.create_index([("user_id", 1), ("last_active_at", -1)])
    await db.stylist_messages.create_index([("session_id", 1), ("created_at", -1)])

    await db.embeddings.create_index(
        [("entity_type", 1), ("entity_id", 1)], unique=True
    )

    await db.cultural_rules.create_index(
        [("region", 1), ("religion", 1), ("occasion", 1)]
    )
    await db.trend_reports.create_index([("date", -1), ("bucket", 1)])
    await db.trend_reports.create_index(
        [("bucket", 1), ("date", 1)], unique=True
    )
    logger.info("MongoDB indexes ensured")


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None
