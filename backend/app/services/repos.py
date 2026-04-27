"""Tiny CRUD helpers on top of Motor collections.

We keep these dumb on purpose: Pydantic does all validation, these helpers
just translate documents to/from Mongo safely and strip `_id`.
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection


def strip_id(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def insert(coll: AsyncIOMotorCollection, doc: dict[str, Any]) -> dict[str, Any]:
    await coll.insert_one({**doc})
    return strip_id(dict(doc))  # type: ignore[return-value]


async def find_one(
    coll: AsyncIOMotorCollection, query: dict[str, Any]
) -> dict[str, Any] | None:
    return strip_id(await coll.find_one(query, {"_id": 0}))


async def find_many(
    coll: AsyncIOMotorCollection,
    query: dict[str, Any],
    *,
    sort: list[tuple[str, int]] | None = None,
    limit: int = 100,
    skip: int = 0,
) -> list[dict[str, Any]]:
    cursor = coll.find(query, {"_id": 0})
    if sort:
        # Atlas M0 imposes a 32 MB in-memory sort cap. Closet documents
        # carry base64 crop thumbnails + reconstruction payloads, so the
        # sort buffer easily blows through that limit. `allow_disk_use`
        # lets Mongo spill the sort to disk (no-op and cost-free when
        # the query is already served by an index).
        cursor = cursor.sort(sort).allow_disk_use(True)
    if skip:
        cursor = cursor.skip(skip)
    cursor = cursor.limit(limit)
    return [d async for d in cursor]


async def update(
    coll: AsyncIOMotorCollection,
    query: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    await coll.update_one(query, {"$set": patch})
    return await find_one(coll, query)


async def delete(coll: AsyncIOMotorCollection, query: dict[str, Any]) -> int:
    result = await coll.delete_one(query)
    return result.deleted_count


async def count(coll: AsyncIOMotorCollection, query: dict[str, Any]) -> int:
    return await coll.count_documents(query)
