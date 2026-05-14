"""Eyes provider override — runtime DB-backed feature flag.

By default the closet vision pipeline reads ``settings.EYES_PROVIDER``
(an env var, frozen at process start). To let admins flip pods between
the self-hosted Gemma-4 E2B path (production) and the Gemini-2.5-Flash
fallback path (preview / disaster recovery) WITHOUT restarting the
backend, we layer a Mongo override on top:

    final_provider = mongo.config.eyes_provider OR settings.EYES_PROVIDER

The override is stored in the singleton document
``config.{_id: "eyes_provider"}`` with shape::

    {
        "_id":        "eyes_provider",
        "value":      "gemma" | "gemini",   # the override
        "updated_at": "<iso8601>",
        "updated_by": "<email>",            # whoever flipped the switch
    }

Read path (hot — runs on every garment analyze):
  * 5-second module-level cache to avoid hammering Mongo.
  * Cache miss -> single ``find_one`` against the config collection.
  * Any DB error -> log + fall back to env (closet pipeline never breaks
    because the override layer is unavailable).

Write path (cold — admin clicks the Profile toggle):
  * ``set_override`` upserts the document and immediately busts the
    cache so the next analyze call sees the new value.
  * Pass ``value=None`` to clear the override and revert to env-default.

Pod scope: each backend process keeps its own cache, but ALL pods share
the same Mongo document. So flipping the switch in one pod propagates
to all pods within ~5 s (the TTL). The user explicitly asked for
**per-pod** scope, so we deliberately do NOT broadcast — every pod's
admin can override its own pod's behaviour by writing to its OWN
``config`` collection (which is per-DB; if multiple pods share a DB,
they share the override). To get true per-pod isolation, run them on
distinct ``DB_NAME`` values, which is already how Hetzner-prod and the
Emergent preview pod are configured (``dressapp_prod`` vs ``test_db``).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.db.database import get_db

log = logging.getLogger(__name__)

_CONFIG_DOC_ID = "eyes_provider"
# Phase O.4 — DressApp ships only the self-hosted Gemma-4 E2B Eyes
# model and Google's Gemini 2.5 Flash. Any other persisted value
# (legacy "qwen", typos, etc.) falls through to the env default at
# resolution time.
_VALID_PROVIDERS = ("gemma", "gemini")
_CACHE_TTL_S = 5.0

# Module-level cache. None until first read; (value, ts) afterwards.
# ``value`` is the *override* (string) or None when no override is set.
_cache: dict[str, Any] = {"value": None, "ts": 0.0, "loaded": False}


def _normalize(value: str | None) -> str | None:
    """Strip + lowercase, return None for blank/invalid values."""
    if not value:
        return None
    v = str(value).strip().lower()
    if v not in _VALID_PROVIDERS:
        return None
    return v


async def _load_override_from_db() -> str | None:
    """Single-shot read of the override doc. Returns None on miss/error."""
    try:
        db = get_db()
        doc = await db.config.find_one({"_id": _CONFIG_DOC_ID})
    except Exception as exc:  # noqa: BLE001
        # DB unavailable / not yet connected — fall through silently
        # so the analyze hot path never raises just because of the
        # override layer.
        log.debug("eyes override DB read failed: %s", exc)
        return None
    if not doc:
        return None
    return _normalize(doc.get("value"))


async def get_active_provider() -> str:
    """Resolve the currently-active Eyes provider.

    Caches the DB lookup for ``_CACHE_TTL_S`` seconds so the closet
    pipeline can call this on every analyze without DB pressure.
    Falls back to ``settings.EYES_PROVIDER`` (env) when no override
    is set, the override is invalid, or the DB read fails.
    """
    now = time.time()
    if _cache["loaded"] and (now - _cache["ts"]) < _CACHE_TTL_S:
        override = _cache["value"]
    else:
        override = await _load_override_from_db()
        _cache["value"] = override
        _cache["ts"] = now
        _cache["loaded"] = True

    if override:
        return override
    # When no DB override is set, fall back to the env-default. The
    # only two supported Eyes backends today are Gemma-4 and Gemini —
    # we bias to "gemini" so a missing/typo env never 503s the pipeline.
    return _normalize(settings.EYES_PROVIDER) or "gemini"


async def set_override(value: str | None, *, by_email: str | None = None) -> dict[str, Any]:
    """Persist a new override (or clear it when ``value`` is None).

    Returns the resulting ``status`` payload (same shape as ``status()``)
    so callers don't need a second round-trip to refresh their UI.
    """
    db = get_db()
    normalized = _normalize(value) if value is not None else None

    if normalized is None and value not in (None, ""):
        # Caller passed a non-empty string that didn't match the allow-list.
        raise ValueError(
            f"invalid provider {value!r} — expected one of {_VALID_PROVIDERS} or null"
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    if normalized is None:
        # Clear override -> delete the document so subsequent reads
        # fall through to env-default.
        await db.config.delete_one({"_id": _CONFIG_DOC_ID})
        log.info(
            "eyes override cleared by %s; reverting to env=%s",
            by_email or "unknown", settings.EYES_PROVIDER,
        )
    else:
        await db.config.update_one(
            {"_id": _CONFIG_DOC_ID},
            {
                "$set": {
                    "value": normalized,
                    "updated_at": now_iso,
                    "updated_by": (by_email or "").lower() or None,
                },
            },
            upsert=True,
        )
        log.info(
            "eyes override set to %s by %s (env default was %s)",
            normalized, by_email or "unknown", settings.EYES_PROVIDER,
        )

    # Bust the cache immediately so the very next analyze call sees
    # the new value (instead of waiting up to 5 s for the TTL).
    _cache["value"] = normalized
    _cache["ts"] = time.time()
    _cache["loaded"] = True

    return await status()


async def status() -> dict[str, Any]:
    """Return the current resolution + metadata for the admin UI.

    Shape::

        {
          "active_provider": "gemma" | "gemini",
          "source":          "db" | "env",
          "env_default":     "gemini",
          "override":        "gemma" | None,
          "updated_at":      "<iso8601>" | None,
          "updated_by":      "<email>"   | None,
          "gemma_url_set":   true,
          "gemma_url":       "http://eyes:7860",   # safe to expose: internal-only
          "api_token_set":   true,
        }
    """
    try:
        db = get_db()
        doc = await db.config.find_one({"_id": _CONFIG_DOC_ID})
    except Exception as exc:  # noqa: BLE001
        log.warning("eyes status DB read failed: %s", exc)
        doc = None

    override = _normalize((doc or {}).get("value")) if doc else None
    env_default = _normalize(settings.EYES_PROVIDER) or "gemini"
    active = override or env_default
    source = "db" if override else "env"

    return {
        "active_provider": active,
        "source": source,
        "env_default": env_default,
        "override": override,
        "updated_at": (doc or {}).get("updated_at"),
        "updated_by": (doc or {}).get("updated_by"),
        "gemma_url_set": bool(settings.EYES_GEMMA_SPACE_URL),
        # Safe to expose because the URL is intended to be a private
        # internal docker hostname (``http://eyes:7860``) on prod or
        # a public hf.space URL on legacy deploys — neither leaks
        # secrets. We deliberately do NOT expose ``EYES_API_TOKEN``
        # or ``EYES_HF_TOKEN``.
        "gemma_url": settings.EYES_GEMMA_SPACE_URL or None,
        "api_token_set": bool(settings.EYES_API_TOKEN or settings.EYES_HF_TOKEN),
    }


def reset_cache() -> None:
    """Test hook — wipe the in-memory cache."""
    _cache["value"] = None
    _cache["ts"] = 0.0
    _cache["loaded"] = False
