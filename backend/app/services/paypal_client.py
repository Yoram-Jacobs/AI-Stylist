"""PayPal REST v2 client service.

Hand-rolled httpx client because `paypalcheckoutsdk` is deprecated
(GitHub archived 2024) and the officially-recommended Python "server-sdk"
is still in beta. REST v2 is stable and well-documented.

Responsibilities:
- Resolve env (sandbox|live) + auth credentials
- Cache OAuth2 access_token in-memory until ~60s before expiry
- Expose high-level helpers: create_order, capture_order,
  create_payout, verify_webhook_signature
- Emit provider_activity records so the admin dashboard can observe
  latency/error rate just like Gemini / HF.
"""
from __future__ import annotations

import base64
import logging
import time
import uuid
from typing import Any

import httpx

from app.config import settings
from app.services import provider_activity

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_MOCK_TOKEN = "MOCK_TOKEN"


def _is_mock_token(tok: str) -> bool:
    return tok == _MOCK_TOKEN


class PayPalError(RuntimeError):
    """Raised for any non-2xx PayPal response."""

    def __init__(self, status: int, body: Any, *, message: str | None = None):
        self.status = status
        self.body = body
        super().__init__(message or f"PayPal API error {status}: {body}")


class _TokenCache:
    """Tiny in-memory bearer cache. Cleared on backend restart — that's fine;
    PayPal tokens live 9 hours so refresh pressure is low either way."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.expires_at: float = 0.0

    def get(self) -> str | None:
        if self.token and time.time() < self.expires_at - 60:
            return self.token
        return None

    def set(self, token: str, expires_in: int) -> None:
        self.token = token
        self.expires_at = time.time() + float(expires_in)


_token_cache = _TokenCache()


def is_configured() -> bool:
    """Cheap check used by route guards to return a friendly 503."""
    return bool(settings.paypal_client_id and settings.paypal_secret)


async def _get_access_token() -> str:
    cached = _token_cache.get()
    if cached:
        return cached
    if not is_configured():
        if settings.PAYPAL_MOCK_MODE:
            return _MOCK_TOKEN
        raise PayPalError(
            503,
            "PayPal credentials missing",
            message=(
                "PAYPAL_ENV="
                f"{settings.PAYPAL_ENV} but no matching "
                "CLIENT_ID/SECRET is configured. Populate /app/backend/.env."
            ),
        )
    basic = base64.b64encode(
        f"{settings.paypal_client_id}:{settings.paypal_secret}".encode()
    ).decode()
    started = time.time()
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as c:
        resp = await c.post(
            f"{settings.paypal_api_base}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"grant_type": "client_credentials"},
        )
    provider_activity.record(
        "paypal",
        ok=resp.status_code == 200,
        latency_ms=int((time.time() - started) * 1000),
        extra={"path": "/v1/oauth2/token"},
    )
    if resp.status_code != 200:
        if settings.PAYPAL_MOCK_MODE:
            logger.warning(
                "PayPal auth failed (%s) — falling back to MOCK MODE. Fix credentials for real flow.",
                resp.status_code,
            )
            _token_cache.set(_MOCK_TOKEN, 3600)
            return _MOCK_TOKEN
        raise PayPalError(resp.status_code, resp.text)
    data = resp.json()
    _token_cache.set(data["access_token"], int(data.get("expires_in", 3600)))
    return data["access_token"]


async def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    extra_headers: dict[str, str] | None = None,
    expect_status: tuple[int, ...] = (200, 201, 202, 204),
) -> dict[str, Any]:
    token = await _get_access_token()
    url = f"{settings.paypal_api_base}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    started = time.time()
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as c:
        resp = await c.request(method, url, headers=headers, json=json)
    provider_activity.record(
        "paypal",
        ok=resp.status_code in expect_status,
        latency_ms=int((time.time() - started) * 1000),
        extra={"path": path, "method": method},
    )
    if resp.status_code not in expect_status:
        logger.warning(
            "PayPal %s %s → %s %s", method, path, resp.status_code, resp.text[:400]
        )
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = resp.text
        raise PayPalError(resp.status_code, body)
    if resp.status_code == 204:
        return {}
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"raw": resp.text}


# --------------------- Orders v2 ---------------------
def _format_amount(amount_cents: int, currency: str) -> dict[str, str]:
    # PayPal expects 2-decimal strings for USD, EUR, etc. JPY/KRW/etc have
    # no decimal places but we're not supporting those in the MVP.
    value = f"{amount_cents / 100:.2f}"
    return {"currency_code": currency.upper(), "value": value}


async def create_order(
    *,
    amount_cents: int,
    currency: str,
    reference_id: str,
    description: str | None = None,
    return_url: str | None = None,
    cancel_url: str | None = None,
    custom_id: str | None = None,
) -> dict[str, Any]:
    """Create a PayPal Orders v2 order with intent=CAPTURE."""
    token = await _get_access_token()
    if _is_mock_token(token):
        mock_id = f"MOCK-{uuid.uuid4().hex[:17].upper()}"
        logger.info("[PAYPAL MOCK] create_order %s for %s %s", mock_id, currency, amount_cents)
        return {
            "id": mock_id,
            "status": "CREATED",
            "mock": True,
            "links": [],
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "amount": _format_amount(amount_cents, currency),
                }
            ],
        }
    body: dict[str, Any] = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference_id[:256],
                "amount": _format_amount(amount_cents, currency),
                **({"description": description[:127]} if description else {}),
                **({"custom_id": custom_id[:127]} if custom_id else {}),
            }
        ],
    }
    ctx: dict[str, Any] = {
        "shipping_preference": "NO_SHIPPING",
        "user_action": "PAY_NOW",
        "brand_name": "DressApp",
    }
    if return_url:
        ctx["return_url"] = return_url
    if cancel_url:
        ctx["cancel_url"] = cancel_url
    body["application_context"] = ctx
    return await _request("POST", "/v2/checkout/orders", json=body)


async def capture_order(order_id: str) -> dict[str, Any]:
    token = await _get_access_token()
    if _is_mock_token(token) or order_id.startswith("MOCK-"):
        mock_capture_id = f"MOCKCAP-{uuid.uuid4().hex[:14].upper()}"
        logger.info("[PAYPAL MOCK] capture_order %s → %s", order_id, mock_capture_id)
        return {
            "id": order_id,
            "status": "COMPLETED",
            "mock": True,
            "payer": {
                "email_address": "mock-buyer@example.com",
                "payer_id": "MOCKPAYER",
            },
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": mock_capture_id,
                                "status": "COMPLETED",
                            }
                        ]
                    }
                }
            ],
        }
    return await _request(
        "POST",
        f"/v2/checkout/orders/{order_id}/capture",
        json={},
    )


async def get_order(order_id: str) -> dict[str, Any]:
    token = await _get_access_token()
    if _is_mock_token(token) or order_id.startswith("MOCK-"):
        return {"id": order_id, "status": "CREATED", "mock": True}
    return await _request("GET", f"/v2/checkout/orders/{order_id}")


# --------------------- Payouts v1 ---------------------
async def create_payout(
    *,
    sender_batch_id: str,
    receiver_email: str,
    amount_cents: int,
    currency: str,
    note: str | None = None,
    sender_item_id: str | None = None,
) -> dict[str, Any]:
    """Create a single-item payout batch to the given PayPal email."""
    token = await _get_access_token()
    if _is_mock_token(token):
        batch = f"MOCKPAYOUT-{uuid.uuid4().hex[:12].upper()}"
        logger.info(
            "[PAYPAL MOCK] create_payout %s %s %s → %s (batch=%s)",
            currency,
            amount_cents,
            receiver_email,
            sender_item_id,
            batch,
        )
        return {
            "batch_header": {
                "payout_batch_id": batch,
                "batch_status": "PENDING",
                "sender_batch_header": {"sender_batch_id": sender_batch_id},
            },
            "mock": True,
        }
    body = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": "You have a payment from DressApp",
            "email_message": note
            or "Your DressApp seller payout is on its way. Thank you!",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": _format_amount(amount_cents, currency),
                "receiver": receiver_email,
                "note": note or "DressApp seller payout",
                "sender_item_id": sender_item_id or sender_batch_id,
            }
        ],
    }
    return await _request("POST", "/v1/payments/payouts", json=body)


async def get_payout_batch(batch_id: str) -> dict[str, Any]:
    return await _request("GET", f"/v1/payments/payouts/{batch_id}")


# --------------------- Webhooks ---------------------
async def verify_webhook_signature(
    *,
    headers: dict[str, str],
    body: dict[str, Any],
) -> bool:
    """Call /v1/notifications/verify-webhook-signature with the raw event.

    Returns True only if PayPal confirms the signature. When
    PAYPAL_SKIP_WEBHOOK_VERIFY=true (dev), always returns True.
    """
    if settings.PAYPAL_SKIP_WEBHOOK_VERIFY:
        logger.warning("PayPal webhook verify skipped via env flag")
        return True
    webhook_id = settings.paypal_webhook_id
    if not webhook_id:
        logger.warning(
            "PayPal webhook_id not set for env=%s; cannot verify signature",
            settings.PAYPAL_ENV,
        )
        return False
    try:
        payload = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": body,
        }
        resp = await _request(
            "POST", "/v1/notifications/verify-webhook-signature", json=payload
        )
        return resp.get("verification_status") == "SUCCESS"
    except PayPalError:
        return False


def public_config() -> dict[str, Any]:
    """Config surface for the frontend PayPal JS SDK loader."""
    return {
        "env": settings.PAYPAL_ENV,
        "client_id": settings.paypal_client_id or "",
        "configured": is_configured(),
        "mock_mode": settings.PAYPAL_MOCK_MODE,
        "default_currency": settings.PAYPAL_DEFAULT_CURRENCY,
        "supported_currencies": [
            c.strip().upper()
            for c in settings.PAYPAL_SUPPORTED_CURRENCIES.split(",")
            if c.strip()
        ],
    }
