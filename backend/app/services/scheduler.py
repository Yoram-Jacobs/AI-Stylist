"""APScheduler boot \u2014 schedules the Trend-Scout agent."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.trend_scout import run_trend_scout

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    try:
        h_s, m_s = hhmm.split(":", 1)
        h, m = int(h_s), int(m_s)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:  # noqa: BLE001
        pass
    logger.warning("Bad TREND_SCOUT_SCHEDULE_UTC=%s; defaulting to 07:00", hhmm)
    return 7, 0


async def _safe_run() -> None:
    try:
        result = await run_trend_scout()
        logger.info(
            "Trend-Scout daily run: generated=%d skipped=%d date=%s",
            len(result.get("generated") or []),
            len(result.get("skipped") or []),
            result.get("date"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trend-Scout daily run failed: %s", exc)


def start_scheduler() -> None:
    """Start the APScheduler singleton. Safe to call multiple times."""
    global _scheduler
    if not settings.TREND_SCOUT_ENABLED:
        logger.info("Trend-Scout scheduler disabled via TREND_SCOUT_ENABLED=false")
        return
    if _scheduler and _scheduler.running:
        return
    hour, minute = _parse_hhmm(settings.TREND_SCOUT_SCHEDULE_UTC)
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _safe_run,
        CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="trend_scout_daily",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "Trend-Scout scheduler started (daily at %02d:%02d UTC)", hour, minute
    )
    if settings.TREND_SCOUT_RUN_ON_STARTUP:
        # Fire-and-forget; never block server startup.
        asyncio.create_task(_safe_run())


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scheduler shutdown error: %s", exc)
    _scheduler = None
