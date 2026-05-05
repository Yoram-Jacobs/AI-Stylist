"""Alibaba DashScope Qwen-VL async client.

Thin, dependency-free wrapper around the DashScope multimodal
generation HTTP API. We talk directly via ``httpx`` (rather than the
``dashscope`` SDK) so every call is properly awaitable inside
FastAPI without thread-pool spillage.

Scope for Phase O.1 (Stylist brain): *chat* with optional image input.
Image classification / detection endpoints used by ``garment_vision``
will reuse this same module in O.2 — they only need a different prompt
and a tighter JSON-schema postprocessing step.

Security note: base64 images are sent inline per the DashScope docs
(``data:<mime>;base64,<payload>``). No images are logged; only metadata
(model, length, elapsed, has_image) appears in the structured log
line so we can debug latency without leaking PII.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Default timeout: stylist chat with an image ranges 2-8s on qwen-vl-max-latest,
# but full-context (closet summary + weather + calendar + prefs + image) calls
# have occasionally been seen taking 30-45s under load. 60s keeps us inside
# the preview gateway ceiling while tolerating real-world bursts. Callers that
# want tighter SLOs can pass ``timeout_s`` to :func:`QwenClient.chat`.
_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Retry schedule — DashScope occasionally returns 429/500 under load; a
# short exponential backoff resolves these without user-visible errors.
_RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
_RETRY_DELAYS = (0.4, 1.0, 2.2)  # three retries, total ~3.6s extra max


class QwenError(RuntimeError):
    """Raised when DashScope returns a hard error that callers should handle.

    ``status`` mirrors the HTTP status; ``code`` / ``message`` come
    straight from DashScope's JSON body when available so upstream
    logs can pin down quota vs. auth vs. model-name issues fast.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


@dataclass
class QwenMessage:
    """One turn in a multimodal chat.

    ``role`` is one of ``"user" | "assistant" | "system"``. ``text`` is
    the prose portion; ``images`` is an optional list of pre-formatted
    ``data:<mime>;base64,<payload>`` strings (use ``encode_image`` to
    produce them).
    """

    role: str
    text: str | None = None
    images: Sequence[str] = ()


def encode_image(base64_payload: str, mime_type: str = "image/jpeg") -> str:
    """Wrap a raw base64 payload in DashScope's expected data URI form.

    Accepts strings that already include a ``data:`` prefix (the
    frontend sometimes sends them that way) and rewrites them cleanly
    so DashScope never receives a doubled prefix.
    """
    payload = (base64_payload or "").strip()
    if payload.startswith("data:"):
        # Strip any existing prefix so we can recompose with a known
        # mime type. ``split(',', 1)[1]`` isolates the base64 body.
        payload = payload.split(",", 1)[-1]
    mime = (mime_type or "image/jpeg").strip() or "image/jpeg"
    if not mime.startswith("image/"):
        mime = f"image/{mime}"
    return f"data:{mime};base64,{payload}"


def _messages_to_dashscope(messages: Sequence[QwenMessage]) -> list[dict[str, Any]]:
    """Convert our lightweight message structs into DashScope wire format.

    DashScope multimodal takes ``content`` as a LIST of mini-parts;
    each part is either ``{"image": "<data-uri>"}`` or ``{"text": ...}``.
    Images are placed FIRST so the model associates the text with the
    image(s) it accompanies — matches the reference examples in the
    DashScope docs.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        parts: list[dict[str, Any]] = []
        for img in msg.images or ():
            if img:
                parts.append({"image": img})
        if msg.text:
            parts.append({"text": msg.text})
        if not parts:
            # DashScope rejects empty content arrays; skip silently.
            continue
        out.append({"role": msg.role, "content": parts})
    return out


class QwenClient:
    """Singleton-ish async client. Cheap to construct; reuses an
    ``httpx.AsyncClient`` across calls for connection pooling."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.DASHSCOPE_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not configured. Add it to backend/.env "
                "and restart. Keys from the Singapore/International console "
                "begin with 'sk-' and pair with the dashscope-intl endpoint."
            )
        self.base_url = (base_url or settings.DASHSCOPE_BASE_URL).rstrip("/")
        self._endpoint = (
            f"{self.base_url}/services/aigc/multimodal-generation/generation"
        )
        # Single shared client — httpx handles per-request cancellation
        # so we don't need a pool per call site.
        self._http = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---------------------------------------------------------------
    # Primary entrypoint
    # ---------------------------------------------------------------
    async def chat(
        self,
        messages: Sequence[QwenMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        response_format_json: bool = False,
        extra_parameters: dict[str, Any] | None = None,
    ) -> str:
        """Send a multimodal chat and return the assistant's raw text.

        ``response_format_json=True`` nudges DashScope to emit strict
        JSON by attaching ``response_format={"type":"json_object"}`` to
        the parameters block. Callers should STILL validate/parse the
        output because the service enforces this best-effort, not
        strictly.
        """
        resolved_model = model or settings.QWEN_BRAIN_MODEL
        payload: dict[str, Any] = {
            "model": resolved_model,
            "input": {"messages": _messages_to_dashscope(messages)},
            "parameters": {
                "result_format": "message",
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        }
        if response_format_json:
            payload["parameters"]["response_format"] = {"type": "json_object"}
        if extra_parameters:
            payload["parameters"].update(extra_parameters)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.monotonic()
        attempt = 0
        last_exc: Exception | None = None
        while True:
            attempt += 1
            try:
                resp = await self._http.post(
                    self._endpoint, headers=headers, json=payload
                )
            except httpx.ConnectError as exc:
                # Genuine network blip — worth retrying.
                last_exc = exc
                logger.warning(
                    "qwen connect error attempt=%d model=%s err=%s",
                    attempt, resolved_model, repr(exc),
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                # Read/write timeout on a working socket = the upstream
                # is genuinely slow. Retrying another full-timeout cycle
                # would push us past the preview gateway cap, so we
                # give up immediately and let the caller fall back.
                logger.warning(
                    "qwen request timed out after attempt=%d model=%s "
                    "err_type=%s err=%s — not retrying",
                    attempt, resolved_model,
                    type(exc).__name__, repr(exc),
                )
                raise QwenError(
                    f"DashScope {resolved_model} timed out.",
                    status=504,
                ) from exc
            else:
                if resp.status_code == 200:
                    body = resp.json()
                    text = _extract_text(body)
                    elapsed = round((time.monotonic() - started) * 1000, 1)
                    logger.info(
                        "qwen chat ok model=%s attempts=%d latency_ms=%s "
                        "tokens_in=%s tokens_out=%s has_image=%s",
                        resolved_model,
                        attempt,
                        elapsed,
                        (body.get("usage") or {}).get("input_tokens"),
                        (body.get("usage") or {}).get("output_tokens"),
                        any(m.images for m in messages),
                    )
                    return text
                # Non-200: decide retry vs raise.
                last_exc = _raise_from_http(resp)

            if attempt > len(_RETRY_DELAYS):
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])

        # Exhausted retries — surface the last failure.
        if isinstance(last_exc, QwenError):
            raise last_exc
        raise QwenError(
            f"Qwen chat failed after {attempt} attempts: {last_exc!r}",
        )


def _extract_text(body: dict[str, Any]) -> str:
    """Flatten DashScope's nested response down to a single string.

    Shape (successful call)::
        {
          "output": {
            "choices": [
              {"message": {"role": "assistant",
                           "content": [{"text": "..."}, ...]}}
            ]
          },
          "usage": {...}
        }

    Any unexpected shape triggers a QwenError so callers don't silently
    get an empty string.
    """
    try:
        choices = body["output"]["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise QwenError(
            f"Unexpected DashScope response shape: {body!r}"
        ) from exc

    # ``content`` can be either a list of part-dicts or (rare) a plain
    # string. We normalise both.
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            part.get("text", "") for part in content if isinstance(part, dict)
        ]
        return "".join(t for t in texts if t).strip()
    raise QwenError(f"Unrecognised content type: {type(content).__name__}")


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_lenient(raw: str) -> dict[str, Any]:
    """Best-effort JSON parse mirroring ``gemini_stylist._parse_json``.

    Strips markdown fences, tries direct parse, then looks for the
    first ``{...}`` run. Returns an empty dict if everything fails so
    the caller can fall back to a "parser could not decode" shell
    instead of 500-ing the request.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


def _raise_from_http(resp: httpx.Response) -> QwenError:
    """Build a QwenError from an HTTP failure response.

    Returns (rather than raises) so the retry loop can decide whether
    to attempt another call before giving up.
    """
    try:
        body = resp.json()
    except json.JSONDecodeError:
        body = {}
    err = QwenError(
        body.get("message") or f"DashScope HTTP {resp.status_code}",
        status=resp.status_code,
        code=body.get("code"),
        request_id=body.get("request_id"),
    )
    logger.warning(
        "qwen http error status=%s code=%s request_id=%s message=%s",
        err.status, err.code, err.request_id, err,
    )
    # Retryable errors come back unraised so the caller's loop can retry.
    if resp.status_code in _RETRY_STATUSES:
        return err
    raise err


# Module-level singleton — instantiated lazily so import-time code paths
# without DashScope credentials (e.g. tests) don't crash.
_client: QwenClient | None = None


def get_qwen_client() -> QwenClient:
    global _client
    if _client is None:
        _client = QwenClient()
    return _client
