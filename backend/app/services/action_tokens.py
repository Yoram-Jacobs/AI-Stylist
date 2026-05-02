"""Action tokens — short-lived JWTs embedded in transactional email links.

Used by Wave 2 marketplace flows (swap accept/deny, donate accept/deny)
so a recipient can act on a transaction directly from their inbox
without logging in. Security model:

* Tokens are signed with the same ``JWT_SECRET`` as auth tokens but use
  a dedicated ``aud`` claim (``"dressapp.tx_action"``) so they can never
  be confused with — or replayed against — bearer auth endpoints.
* Each token carries a random ``jti`` (UUID4) that the issuing endpoint
  persists on the transaction (e.g. ``swap.action_token_jti``). When the
  recipient clicks accept/deny, the action endpoint compares the
  presented ``jti`` against the persisted one and refuses if they
  don't match — that is, every email rotation invalidates older links,
  and a single token can only be spent once before being marked used.
* Default expiry is **24 hours**; emails mention a 7-day window so the
  caller can override per-flow if a future product decision wants
  longer-lived links.

Usage::

    from app.services import action_tokens
    token = action_tokens.mint(
        tx_id=tx.id, role="lister", decision_choices=("accept", "deny")
    )
    # → URL: f"{APP_PUBLIC_URL}/api/v1/transactions/action?token={token}&decision=accept"

    payload = action_tokens.verify(presented_token, expected_decision="accept")
    # → {"tx_id": ..., "role": ..., "jti": ..., "decision_choices": [...]}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

ACTION_AUD = "dressapp.tx_action"


def mint(
    *,
    tx_id: str,
    role: str,
    decision_choices: tuple[str, ...] = ("accept", "deny"),
    expires_hours: int = 24,
) -> tuple[str, str]:
    """Mint a one-shot JWT for an email accept/deny URL.

    Returns ``(token, jti)`` so the caller can persist ``jti`` on the
    transaction and later compare against the value carried by the
    presented token.
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "aud": ACTION_AUD,
        "sub": tx_id,
        "role": role,
        "decision_choices": list(decision_choices),
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    token = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return token, jti


def verify(token: str, *, expected_decision: str | None = None) -> dict[str, Any]:
    """Verify signature, expiry, audience and (optionally) decision.

    Raises ``HTTPException(400/401)`` with a friendly message on failure
    so the action endpoint can surface a sensible landing page rather
    than a stack trace.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            audience=ACTION_AUD,
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status.HTTP_410_GONE,
            "This action link has expired. Please ask the other party to resend.",
        ) from exc
    except jwt.InvalidAudienceError as exc:
        # Auth tokens or other JWTs accidentally pointed at this URL.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid action link."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid or tampered action link."
        ) from exc

    if expected_decision is not None:
        choices = payload.get("decision_choices") or []
        if expected_decision not in choices:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This action is not allowed for this link.",
            )
    return payload
