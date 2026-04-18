"""Stripe Connect Express fee math.

Keeps marketplace pricing logic in one place so the UI, the checkout flow and
the transaction ledger always agree. The “7% buffer” is applied AFTER
Stripe’s processing fee, per the Phase 1 spec.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass
class FeeBreakdown:
    gross_cents: int
    stripe_fee_cents: int
    net_after_stripe_cents: int
    platform_fee_percent: float
    platform_fee_cents: int
    seller_net_cents: int
    platform_fee_applied_after: str = "stripe_processing_fee"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def compute_fees(gross_cents: int) -> FeeBreakdown:
    if gross_cents < 0:
        raise ValueError("gross_cents must be non-negative")
    stripe_pct = settings.STRIPE_PROCESSING_FEE_PERCENT / 100.0
    stripe_fixed = settings.STRIPE_PROCESSING_FEE_FIXED_CENTS
    stripe_fee = int(round(gross_cents * stripe_pct + stripe_fixed))

    net_after_stripe = max(gross_cents - stripe_fee, 0)
    platform_pct = settings.STRIPE_PLATFORM_FEE_PERCENT / 100.0
    platform_fee = int(round(net_after_stripe * platform_pct))

    seller_net = max(net_after_stripe - platform_fee, 0)

    return FeeBreakdown(
        gross_cents=gross_cents,
        stripe_fee_cents=stripe_fee,
        net_after_stripe_cents=net_after_stripe,
        platform_fee_percent=settings.STRIPE_PLATFORM_FEE_PERCENT,
        platform_fee_cents=platform_fee,
        seller_net_cents=seller_net,
    )
