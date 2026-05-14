"""Provider abstraction for the DressApp Stylist Brain.

As of May 2026, the Stylist runs on Google Gemini (``gemini-2.5-pro``
via ``emergentintegrations`` / direct ``GEMINI_API_KEY``). The factory
keeps a thin Protocol-based abstraction so a future fine-tuned
``Gemma4-E4B`` provider can be slotted in without touching call sites
in ``services/logic.py``.

Earlier waves shipped Alibaba Qwen-VL via DashScope as a temporary
primary brain (Wave O.1). That path was removed in May 2026 — see
``docs/WASTED_WORK_REPORT.md §2.2`` for the rationale.

The public entrypoint is :func:`stylist_brain_service`, which picks
the primary provider based on ``settings.STYLIST_PROVIDER`` and wraps
it in :class:`FallbackBrain` if ``settings.STYLIST_FALLBACK`` is set.
Both the primary and the fallback satisfy the same minimal contract:

    async def advise(self, session_id, user_text, image_base64, image_mime,
                     weather, calendar_events, cultural_rules,
                     user_profile, closet_summary,
                     user_preferences_block) -> dict

so callers in ``services/logic.py`` don't know — and don't need to
know — which brain actually produced the recommendation.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import settings
from app.services.gemini_stylist import gemini_stylist_service

logger = logging.getLogger(__name__)


class StylistBrain(Protocol):
    """Structural contract — any concrete provider satisfies this shape."""

    provider_name: str

    async def advise(
        self,
        *,
        session_id: str,
        user_text: str,
        image_base64: str | None,
        image_mime: str = "image/jpeg",
        weather: dict[str, Any] | None = None,
        calendar_events: list[dict[str, Any]] | None = None,
        cultural_rules: list[dict[str, Any]] | None = None,
        user_profile: dict[str, Any] | None = None,
        closet_summary: list[dict[str, Any]] | None = None,
        user_preferences_block: str | None = None,
    ) -> dict[str, Any]:
        ...


# -----------------------------------------------------------------
# Gemini provider — thin adapter so the legacy service satisfies the
# same Protocol as any future provider
# -----------------------------------------------------------------
class GeminiStylistBrain:
    """Adapter around the legacy ``gemini_stylist_service`` singleton."""

    provider_name = "gemini"

    def __init__(self) -> None:
        if gemini_stylist_service is None:
            raise RuntimeError(
                "Gemini stylist service unavailable. Set GEMINI_API_KEY "
                "or EMERGENT_LLM_KEY to enable it."
            )
        self._svc = gemini_stylist_service

    async def advise(self, **kwargs: Any) -> dict[str, Any]:
        return await self._svc.advise(**kwargs)


# -----------------------------------------------------------------
# Fallback chain — try primary, fall back on RuntimeError / Timeout
# -----------------------------------------------------------------
class FallbackBrain:
    """Wraps a ``primary`` brain, falling back to ``fallback`` on error.

    Designed to be conservative: only retryable transport/infrastructure
    errors trigger the fallback path; Pydantic / parse errors upstream
    would still surface so we don't mask genuine contract bugs.
    """

    def __init__(self, primary: StylistBrain, fallback: StylistBrain) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_name = (
            f"{primary.provider_name}+fallback:{fallback.provider_name}"
        )

    async def advise(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return await self.primary.advise(**kwargs)
        except (RuntimeError, TimeoutError) as exc:
            logger.warning(
                "stylist primary provider %s failed (%s); falling back to %s",
                self.primary.provider_name,
                repr(exc)[:200],
                self.fallback.provider_name,
            )
            return await self.fallback.advise(**kwargs)


# -----------------------------------------------------------------
# Factory
# -----------------------------------------------------------------
def _make_provider(name: str) -> StylistBrain | None:
    """Instantiate a concrete brain by name; return None if the
    environment isn't configured to support it."""
    try:
        if name == "gemini":
            if gemini_stylist_service is None:
                logger.info("gemini requested but no Gemini key configured")
                return None
            return GeminiStylistBrain()
        if name in ("", "none"):
            return None
        # Legacy values like "qwen" used to map to a DashScope brain
        # that was retired in May 2026. We accept them silently and
        # fall through to the env-default ``gemini`` path so a stale
        # ``.env`` doesn't 503 the stylist endpoint.
        logger.warning(
            "Unknown / retired STYLIST_PROVIDER value: %r — falling "
            "through to env default", name,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        # A provider init error should NOT crash the whole backend
        # boot — we'd rather log and let the factory fall through to
        # a backup provider.
        logger.exception("Failed to instantiate provider %s: %s", name, exc)
        return None


def build_stylist_brain() -> StylistBrain:
    """Resolve the brain stack based on current settings.

    Order of resolution:
      1. Primary = ``STYLIST_PROVIDER`` (default ``"gemini"``).
      2. Fallback = ``STYLIST_FALLBACK`` (default ``"gemini"``) — only
         attached when the primary is NOT the same provider. Today
         that means fallback is a no-op; it's retained so a future
         Gemma provider can land here with Gemini as its safety net.
      3. If the primary can't be instantiated, the fallback becomes
         the primary so /api/v1/stylist still works.
      4. If neither provider is available, raises ``RuntimeError`` so
         the ``/stylist`` endpoint can surface a clean 503.
    """
    primary_name = settings.STYLIST_PROVIDER.lower().strip() or "gemini"
    fallback_name = settings.STYLIST_FALLBACK.lower().strip()

    primary = _make_provider(primary_name)
    fallback = (
        _make_provider(fallback_name)
        if fallback_name and fallback_name != primary_name
        else None
    )

    if primary is None and fallback is None:
        raise RuntimeError(
            "No stylist brain provider is configured. Set "
            "STYLIST_PROVIDER=gemini and provide GEMINI_API_KEY "
            "(or EMERGENT_LLM_KEY)."
        )
    if primary is None:
        logger.warning(
            "Primary stylist provider %s unavailable; promoting fallback %s",
            primary_name, fallback_name,
        )
        assert fallback is not None
        return fallback
    if fallback is None:
        logger.info(
            "Stylist brain initialised: provider=%s, no fallback configured",
            primary.provider_name,
        )
        return primary
    logger.info(
        "Stylist brain initialised: primary=%s fallback=%s",
        primary.provider_name, fallback.provider_name,
    )
    return FallbackBrain(primary=primary, fallback=fallback)


# Lazy module-level singleton. The factory is cheap, but we avoid
# re-running provider init on every stylist call.
_service: StylistBrain | None = None


def stylist_brain_service() -> StylistBrain:
    global _service
    if _service is None:
        _service = build_stylist_brain()
    return _service


def reset_stylist_brain_service() -> None:
    """Clear the cached singleton. Exposed for tests + ``/admin`` hot-reload."""
    global _service
    _service = None
