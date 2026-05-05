"""Provider abstraction for the DressApp Stylist Brain.

Phase O (as of v1.1.1) moves the Stylist away from Google Gemini and
onto Alibaba Qwen-VL via DashScope, with Gemini retained as a silent
fallback. A future wave will slot the fine-tuned ``Gemma4-E4B`` model
into this same interface once a 24/7 host is in place.

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

import json
import logging
from typing import Any, Protocol

from app.config import settings
from app.services.gemini_stylist import (
    SYSTEM_PROMPT,
    _LANG_NAMES,
    _language_directive,
    _parse_json,
    gemini_stylist_service,
)
from app.services.qwen_client import (
    QwenError,
    QwenMessage,
    encode_image,
    get_qwen_client,
)

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
# Qwen provider — DashScope multimodal chat
# -----------------------------------------------------------------
class QwenStylistBrain:
    """Backs /api/v1/stylist with Qwen-VL-Max-Latest via DashScope.

    Reuses the exact ``SYSTEM_PROMPT`` and language directives from the
    Gemini implementation so outputs stay compatible with the existing
    response parser + UI. The only behavioural difference: DashScope
    occasionally emits JSON wrapped in markdown fences — the shared
    ``_parse_json`` helper already handles that.
    """

    provider_name = "qwen"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.QWEN_BRAIN_MODEL
        self._client = get_qwen_client()

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
        # System prompt construction mirrors the Gemini path exactly so
        # A/B-style comparisons stay valid. Preferences slot in AFTER
        # the JSON contract so the model still treats that contract as
        # non-negotiable.
        sys_msg = SYSTEM_PROMPT + _language_directive(
            (user_profile or {}).get("preferred_language")
        )
        if user_preferences_block:
            sys_msg = sys_msg + "\n\n" + user_preferences_block.strip() + "\n"

        context_block = {
            "weather": weather,
            "calendar_events": calendar_events or [],
            "cultural_rules": cultural_rules or [],
            "user_profile": user_profile or {},
            "closet_summary": closet_summary or [],
        }

        lang_code = (
            (user_profile or {}).get("preferred_language") or "en"
        ).lower()
        lang_name = _LANG_NAMES.get(lang_code, "English")
        if lang_code == "en":
            lang_preamble = ""
        else:
            lang_preamble = (
                f"**OUTPUT LANGUAGE = {lang_name} ({lang_code}).** Every "
                f"free-text field (`reasoning_summary`, each "
                f"recommendation's `name`/`why`, every item `description`, "
                f"every `do_dont` entry, every `shopping_suggestions` "
                f"entry, and the final `spoken_reply`) MUST be written in "
                f"fluent, idiomatic {lang_name}. JSON keys and enum tokens "
                f"stay in English.\n\n"
            )
        prompt_text = (
            f"{lang_preamble}"
            f"USER_REQUEST:\n{user_text}\n\n"
            f"CONTEXT:\n{json.dumps(context_block, ensure_ascii=False, indent=2)}\n\n"
            "Return the JSON object now."
        )

        images: list[str] = []
        if image_base64:
            images.append(encode_image(image_base64, image_mime))

        messages = [
            QwenMessage(role="system", text=sys_msg),
            QwenMessage(role="user", text=prompt_text, images=images),
        ]

        logger.info(
            "qwen stylist call session=%s model=%s has_image=%s",
            session_id, self.model, bool(image_base64),
        )
        from app.services import provider_activity

        with provider_activity.Track(
            "qwen-stylist",
            {"model": self.model, "has_image": bool(image_base64)},
        ):
            # response_format_json nudges DashScope toward clean JSON,
            # but we still run it through the lenient parser in case
            # the model wraps it in fences or prose.
            raw = await self._client.chat(
                messages,
                model=self.model,
                max_tokens=2048,
                temperature=0.5,
                response_format_json=True,
            )
        return _parse_json(raw)


# -----------------------------------------------------------------
# Gemini provider — thin adapter so the legacy service satisfies the
# same Protocol as the newer providers
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
# Fallback chain — try primary, fall back on QwenError / RuntimeError
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
        except (QwenError, RuntimeError, TimeoutError) as exc:
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
        if name == "qwen":
            if not settings.DASHSCOPE_API_KEY:
                logger.info("qwen requested but DASHSCOPE_API_KEY missing")
                return None
            return QwenStylistBrain()
        if name == "gemini":
            if gemini_stylist_service is None:
                logger.info("gemini requested but no Gemini key configured")
                return None
            return GeminiStylistBrain()
        if name in ("", "none"):
            return None
        logger.warning("Unknown STYLIST_PROVIDER value: %r", name)
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
      1. Primary = ``STYLIST_PROVIDER`` (default ``"qwen"``)
      2. Fallback = ``STYLIST_FALLBACK`` (default ``"gemini"``) — only
         attached when the primary is NOT the same provider.
      3. If the primary can't be instantiated, the fallback becomes
         the primary so /api/v1/stylist still works.
      4. If neither provider is available, raises ``RuntimeError`` so
         the ``/stylist`` endpoint can surface a clean 503.
    """
    primary_name = settings.STYLIST_PROVIDER.lower().strip() or "qwen"
    fallback_name = settings.STYLIST_FALLBACK.lower().strip()

    primary = _make_provider(primary_name)
    fallback = (
        _make_provider(fallback_name)
        if fallback_name and fallback_name != primary_name
        else None
    )

    if primary is None and fallback is None:
        raise RuntimeError(
            "No stylist brain provider is configured. Set at least one "
            "of STYLIST_PROVIDER=qwen (with DASHSCOPE_API_KEY) or "
            "STYLIST_PROVIDER=gemini (with GEMINI_API_KEY / "
            "EMERGENT_LLM_KEY)."
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
