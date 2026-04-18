"""OpenWeatherMap client — fetch current conditions and a short forecast.

We use the free `data/2.5/weather` endpoint (current) and `data/2.5/forecast`
(3-hour steps) because the OneCall 3.0 endpoint requires a different plan.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OWM_BASE = "https://api.openweathermap.org/data/2.5"


class WeatherService:
    def __init__(self) -> None:
        if not settings.OPENWEATHER_API_KEY:
            raise RuntimeError("OPENWEATHER_API_KEY is not configured.")
        self.api_key = settings.OPENWEATHER_API_KEY

    async def fetch(self, lat: float, lng: float, units: str = "metric") -> dict[str, Any]:
        params = {
            "lat": lat,
            "lon": lng,
            "units": units,
            "appid": self.api_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            cur_resp = await client.get(f"{OWM_BASE}/weather", params=params)
            fc_resp = await client.get(f"{OWM_BASE}/forecast", params=params)

        cur_resp.raise_for_status()
        fc_resp.raise_for_status()
        current = cur_resp.json()
        forecast = fc_resp.json()

        summary = {
            "temp_c": _safe_get(current, ["main", "temp"]),
            "feels_like_c": _safe_get(current, ["main", "feels_like"]),
            "humidity": _safe_get(current, ["main", "humidity"]),
            "condition": _safe_get(current, ["weather", 0, "main"]),
            "description": _safe_get(current, ["weather", 0, "description"]),
            "wind_speed": _safe_get(current, ["wind", "speed"]),
            "city": current.get("name"),
            "country": _safe_get(current, ["sys", "country"]),
            "forecast_next_24h": _summarize_forecast(forecast.get("list", [])[:8]),
        }
        logger.info(
            "Weather fetched city=%s temp=%s cond=%s",
            summary["city"],
            summary["temp_c"],
            summary["condition"],
        )
        return summary


def _safe_get(d: Any, path: list[Any]) -> Any:
    cur = d
    for key in path:
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return None
    return cur


def _summarize_forecast(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in entries:
        out.append(
            {
                "at": e.get("dt_txt"),
                "temp_c": _safe_get(e, ["main", "temp"]),
                "condition": _safe_get(e, ["weather", 0, "main"]),
                "pop": e.get("pop"),
            }
        )
    return out


weather_service = WeatherService() if settings.OPENWEATHER_API_KEY else None
