"""Lightweight in-memory provider activity tracker.

Captures the last N calls per provider for the Admin dashboard:
* Provider name (gemini-text, hf-image, hf-segformer, deepgram, groq, weather, calendar, etc.)
* Latency in ms
* Success / failure flag
* Optional short error message (truncated)

This is intentionally **process-local**. We accept losing the buffer on
restart in exchange for zero infra (no Redis, no Mongo write-amplification).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

_MAX_PER_PROVIDER = 200
_lock = threading.Lock()
_calls: dict[str, deque[dict[str, Any]]] = defaultdict(
    lambda: deque(maxlen=_MAX_PER_PROVIDER)
)


def record(
    provider: str,
    *,
    ok: bool,
    latency_ms: int,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": bool(ok),
        "latency_ms": int(latency_ms),
        "error": (error or "")[:240] if not ok else None,
    }
    if extra:
        entry.update({k: v for k, v in extra.items() if k not in entry})
    with _lock:
        _calls[provider].append(entry)


def snapshot(provider: str | None = None) -> dict[str, list[dict[str, Any]]]:
    with _lock:
        if provider:
            return {provider: list(_calls.get(provider, deque()))}
        return {k: list(v) for k, v in _calls.items()}


def summary() -> list[dict[str, Any]]:
    """Return aggregate {provider, total, ok, fail, error_rate, avg_ms, p95_ms}."""
    out: list[dict[str, Any]] = []
    with _lock:
        items = {k: list(v) for k, v in _calls.items()}
    for provider, calls in items.items():
        if not calls:
            continue
        latencies = [c["latency_ms"] for c in calls]
        latencies.sort()
        ok = sum(1 for c in calls if c.get("ok"))
        fail = len(calls) - ok
        avg = sum(latencies) / len(latencies)
        p95_idx = max(0, int(len(latencies) * 0.95) - 1)
        out.append(
            {
                "provider": provider,
                "total": len(calls),
                "ok": ok,
                "fail": fail,
                "error_rate": round(fail / len(calls), 4),
                "avg_ms": int(avg),
                "p95_ms": latencies[p95_idx],
                "last_ts": calls[-1]["ts"],
                "last_ok": calls[-1].get("ok"),
                "last_error": calls[-1].get("error"),
            }
        )
    out.sort(key=lambda r: (-r["fail"], -r["total"]))
    return out


class Track:
    """Context manager that records a provider call's outcome and latency.

    Usage:
        async with Track("hf-image"):
            await ...

    Or for sync code, use the bare ``record(...)`` function.
    """

    def __init__(self, provider: str, extra: dict[str, Any] | None = None) -> None:
        self.provider = provider
        self.extra = extra
        self._t0 = 0.0

    def __enter__(self) -> "Track":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        dt = int((time.perf_counter() - self._t0) * 1000)
        record(
            self.provider,
            ok=exc is None,
            latency_ms=dt,
            error=repr(exc) if exc else None,
            extra=self.extra,
        )

    async def __aenter__(self) -> "Track":  # support async with
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        # Mirror the sync exit; never swallow the original exception.
        self.__exit__(exc_type, exc, tb)


def reset() -> None:  # used by tests
    with _lock:
        _calls.clear()
