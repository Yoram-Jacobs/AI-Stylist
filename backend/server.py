"""DressApp FastAPI entrypoint.

Backend scaffold is split across `/app/backend/app/*`. This file only wires
the top-level FastAPI instance, CORS, MongoDB startup/shutdown, and the
`/api/v1` router. Business logic lives in `app/services/*` and route
handlers in `app/api/v1/*`.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Make `app` package importable regardless of launch directory
sys.path.insert(0, str(ROOT_DIR))

from app.api.v1.router import api_v1_router  # noqa: E402
from app.db.database import ensure_indexes, get_client  # noqa: E402
from app.services.scheduler import shutdown_scheduler, start_scheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("dressapp")

# ---- MongoDB (legacy status_checks retained for template compatibility) ----
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="DressApp API", version="0.1.0")
api_router = APIRouter(prefix="/api")


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


@api_router.get("/")
async def root() -> dict:
    return {"message": "DressApp API is live", "docs": "/docs"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate) -> StatusCheck:
    status_obj = StatusCheck(**input.model_dump())
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks() -> List[StatusCheck]:
    checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in checks:
        if isinstance(check.get("timestamp"), str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])
    return checks


# Mount the v1 router under /api/v1
api_router.include_router(api_v1_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    try:
        # Use Motor client from app.db so indexes live on the shared client
        _ = get_client()
        await ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Index bootstrap skipped: %s", exc)
    try:
        start_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduler start skipped: %s", exc)


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    try:
        shutdown_scheduler()
    except Exception:  # noqa: BLE001
        pass
    client.close()
