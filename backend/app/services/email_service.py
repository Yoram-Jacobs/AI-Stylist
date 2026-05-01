"""Email service — Resend-backed transactional emails for the
DressApp marketplace.

Six template families are exposed at the top level. Each one builds a
fully self-contained HTML email (tables + inline CSS, no external
stylesheets — the way email clients still want it) and dispatches it
asynchronously so we never block the request hot-path:

    * sale_seller(...)        — congratulate seller after a paid sale
    * sale_buyer(...)         — congratulate buyer after a purchase
    * swap_request(...)       — invite lister to accept/deny a swap
    * swap_success(...)       — both parties confirm receipt
    * swap_denied(...)        — lister rejected the swap
    * donation_both(...)      — donor + recipient confirmation

Every template ends with the same green-credentials paragraph so the
contributor message stays consistent across flows. Contact details are
rendered with graceful degradation — missing fields are simply skipped
rather than printed as "None" or empty rows.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import resend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resend client setup. We initialise lazily so unit tests / dev pods
# without a key don't crash on import.
# ---------------------------------------------------------------------------
_RESEND_KEY = os.environ.get("RESEND_API_KEY", "").strip()
_SENDER = os.environ.get("SENDER_EMAIL", "hello@dressapp.co").strip()
_APP_URL = os.environ.get("APP_PUBLIC_URL", "https://dressapp.co").rstrip("/")
_BRAND_NAME = "DressApp"
_BRAND_COLOR = "#1F6F6B"   # primary teal
_ACCENT = "#C2553A"         # warm clay accent for CTAs
_BG = "#F7F4EE"             # cream

if _RESEND_KEY:
    resend.api_key = _RESEND_KEY


def is_configured() -> bool:
    """True iff the env has a usable Resend API key."""
    return bool(_RESEND_KEY)


# ---------------------------------------------------------------------------
# Async send wrapper. The Resend SDK is sync; we run it in a thread so
# FastAPI's event loop stays free. Failures are LOGGED and SWALLOWED —
# we never want a transactional payment to 500 because an SMTP server
# blinked. Callers can inspect the returned dict for a {"id": ...} on
# success or {"error": "..."} on failure.
# ---------------------------------------------------------------------------
async def _send(
    to: str | list[str],
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
) -> dict[str, Any]:
    if not is_configured():
        logger.warning("email skipped — RESEND_API_KEY not set: subj=%r", subject)
        return {"error": "RESEND_API_KEY not configured"}
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        return {"error": "no recipients"}
    params: dict[str, Any] = {
        "from": f"{_BRAND_NAME} <{_SENDER}>",
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        params["reply_to"] = reply_to
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        eid = result.get("id") if isinstance(result, dict) else None
        logger.info("email sent id=%s subj=%r to=%s", eid, subject, recipients)
        return {"id": eid}
    except Exception as exc:  # noqa: BLE001
        logger.warning("email send failed subj=%r err=%r", subject, exc)
        return {"error": repr(exc)}


# ---------------------------------------------------------------------------
# Layout helpers — share a common header/footer so brand voice stays
# consistent without copy-pasting markup into every template.
# ---------------------------------------------------------------------------
_GREEN_PRAISE = (
    "By choosing pre-loved fashion, you helped reduce the textile industry's "
    "carbon footprint, water consumption, and chemical pollution. Every "
    "garment given a second life is one less ending up in a landfill — and "
    "that matters."
)


def _wrap(content_html: str, *, preheader: str = "") -> str:
    """Wrap inner content in the standard email skeleton."""
    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_BRAND_NAME}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:Helvetica,Arial,sans-serif;color:#222;">
<span style="display:none!important;font-size:1px;color:{_BG};opacity:0;">{preheader}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0"
           style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;
                  box-shadow:0 1px 3px rgba(0,0,0,.06);">
      <tr><td style="padding:28px 32px 12px 32px;border-bottom:1px solid #eee;">
        <table role="presentation" width="100%"><tr>
          <td style="font-family:'Gloock','Times New Roman',serif;font-size:28px;color:{_BRAND_COLOR};">
            DressApp
          </td>
          <td align="right" style="font-size:12px;color:#888;letter-spacing:.06em;text-transform:uppercase;">
            Your circular wardrobe
          </td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:28px 32px 12px 32px;font-size:15px;line-height:1.55;">
        {content_html}
      </td></tr>
      <tr><td style="padding:18px 32px 28px 32px;border-top:1px solid #eee;
                     font-size:12px;color:#888;line-height:1.5;">
        <p style="margin:0 0 6px;color:#5a8b87;">{_GREEN_PRAISE}</p>
        <p style="margin:6px 0 0;">
          Sent by {_BRAND_NAME} ·
          <a href="{_APP_URL}" style="color:{_BRAND_COLOR};text-decoration:none;">dressapp.co</a>
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>
"""


def _btn(label: str, href: str, *, color: str = _BRAND_COLOR) -> str:
    """Bullet-proof email button — uses tables for outlook compatibility."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:16px 0;"><tr>'
        f'<td bgcolor="{color}" style="border-radius:8px;">'
        f'<a href="{href}" target="_blank" '
        f'style="display:inline-block;padding:12px 24px;color:#ffffff;'
        f'font-weight:600;text-decoration:none;font-size:14px;'
        f'border-radius:8px;">{label}</a>'
        f'</td></tr></table>'
    )


def _item_card(item: dict[str, Any]) -> str:
    """Render a small item preview card (image + title + brand)."""
    title = (item.get("title") or "Untitled item").replace("<", "&lt;")
    brand = (item.get("brand") or "").replace("<", "&lt;")
    img = (
        item.get("thumbnail_data_url")
        or item.get("segmented_image_url")
        or item.get("original_image_url")
        or ""
    )
    img_html = ""
    if img:
        img_html = (
            f'<img src="{img}" alt="" width="120" height="120" '
            f'style="display:block;border:0;border-radius:10px;'
            f'object-fit:cover;background:#eee;">'
        )
    brand_html = (
        f'<div style="color:#888;font-size:12px;margin-top:4px;">{brand}</div>'
        if brand else ""
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="border:1px solid #eee;border-radius:10px;padding:12px;'
        'margin:12px 0;background:#fafafa;"><tr>'
        f'<td valign="top" width="130">{img_html}</td>'
        f'<td valign="top" style="padding-left:14px;">'
        f'<div style="font-weight:600;font-size:15px;">{title}</div>'
        f'{brand_html}'
        '</td></tr></table>'
    )


def _contact_block(label: str, person: dict[str, Any]) -> str:
    """Format a contact card with graceful degradation. Skips missing fields."""
    rows: list[str] = []
    name = person.get("display_name") or person.get("full_name") or person.get("name")
    if name:
        rows.append(f"<strong>{name}</strong>")
    email = person.get("email")
    if email:
        rows.append(f'<a href="mailto:{email}" style="color:{_BRAND_COLOR};">{email}</a>')
    phone = person.get("phone")
    if phone:
        rows.append(phone)
    addr = person.get("address") or {}
    if isinstance(addr, dict):
        for fld in ("line1", "line2"):
            v = addr.get(fld)
            if v:
                rows.append(v)
        line3 = " ".join(
            v for v in (
                addr.get("city"),
                addr.get("region"),
                addr.get("postal_code"),
            ) if v
        )
        if line3:
            rows.append(line3)
        country = addr.get("country")
        if country:
            rows.append(country)
    if not rows:
        # Last-resort fallback so the lister/buyer still has something
        # actionable. Email is always required at signup.
        if email:
            rows.append(f'<a href="mailto:{email}">{email}</a>')
        else:
            rows.append('<em style="color:#aaa;">No contact details on file</em>')
    return (
        f'<div style="margin:14px 0;padding:14px;border-left:3px solid {_BRAND_COLOR};'
        f'background:#f4f9f8;border-radius:6px;">'
        f'<div style="font-size:12px;color:#5a8b87;letter-spacing:.06em;'
        f'text-transform:uppercase;margin-bottom:6px;">{label}</div>'
        + "<br>".join(rows)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Template builders — six flavours. Each accepts `to` (string or list) and
# the relevant context dicts, and dispatches via `_send`.
# ---------------------------------------------------------------------------
async def sale_seller(
    *, to: str, seller: dict, buyer: dict, item: dict, gross_cents: int,
    seller_net_cents: int, currency: str,
) -> dict:
    seller_name = seller.get("display_name") or seller.get("name") or "there"
    gross = f"{currency} {gross_cents/100:.2f}"
    net = f"{currency} {seller_net_cents/100:.2f}"
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">Congratulations on your sale, {seller_name}! 🎉</h1>
<p>Your item just found a new home. Here are the details:</p>
{_item_card(item)}
<p>
  Sale price: <strong>{gross}</strong><br>
  Your payout (after fees): <strong>{net}</strong>
</p>
<p>Please ship the item using the buyer's contact details below. Buyers
expect dispatch within 3 working days.</p>
{_contact_block("Buyer contact", buyer)}
{_btn("View transaction in DressApp", f"{_APP_URL}/transactions")}
"""
    return await _send(to, f"You sold {item.get('title','your item')}!", _wrap(body, preheader="Congrats — please dispatch within 3 days."))


async def sale_buyer(
    *, to: str, buyer: dict, seller: dict, item: dict, gross_cents: int, currency: str,
) -> dict:
    buyer_name = buyer.get("display_name") or buyer.get("name") or "there"
    gross = f"{currency} {gross_cents/100:.2f}"
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">You got it, {buyer_name}! 🛍️</h1>
<p>Your purchase is confirmed. Here are the details:</p>
{_item_card(item)}
<p>You paid: <strong>{gross}</strong></p>
<p>The seller has been notified and will dispatch within 3 working days.
Reach out to them directly if you need to coordinate delivery:</p>
{_contact_block("Seller contact", seller)}
{_btn("View transaction in DressApp", f"{_APP_URL}/transactions")}
"""
    return await _send(to, f"Your purchase: {item.get('title','your new item')}", _wrap(body, preheader="Sale confirmed — seller will dispatch within 3 days."))


async def swap_request(
    *, to: str, lister: dict, swapper: dict, listing_item: dict,
    offered_item: dict, accept_url: str, deny_url: str,
) -> dict:
    lister_name = lister.get("display_name") or lister.get("name") or "there"
    swapper_name = swapper.get("display_name") or swapper.get("name") or "Someone"
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">Hi {lister_name}, you have a swap offer 🔄</h1>
<p><strong>{swapper_name}</strong> would like to swap their item for your listing:</p>
<div style="font-size:12px;color:#888;letter-spacing:.06em;text-transform:uppercase;margin-top:18px;">Your listing</div>
{_item_card(listing_item)}
<div style="font-size:12px;color:#888;letter-spacing:.06em;text-transform:uppercase;margin-top:6px;">In exchange for</div>
{_item_card(offered_item)}
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
  <td>{_btn("Accept swap", accept_url)}</td>
  <td style="width:8px;"></td>
  <td>{_btn("Decline", deny_url, color="#aaa")}</td>
</tr></table>
<p style="font-size:12px;color:#888;">No login required — these links expire in 7 days.</p>
"""
    return await _send(to, f"Swap offer for {listing_item.get('title','your item')}", _wrap(body, preheader=f"{swapper_name} wants to swap with you."))


async def swap_success(
    *, to: str, recipient: dict, counterpart: dict, recipient_item: dict,
    counterpart_item: dict, confirm_url: str, role: str,
) -> dict:
    """Sent to BOTH parties after the swap is accepted. ``role`` is
    "lister" or "swapper" purely to tweak the wording."""
    rec_name = recipient.get("display_name") or recipient.get("name") or "there"
    if role == "lister":
        intro = f"Your swap with <strong>{counterpart.get('display_name') or 'the swapper'}</strong> is on. They will ship you their item below — please ship yours back."
    else:
        intro = f"<strong>{counterpart.get('display_name') or 'The lister'}</strong> accepted your swap. Please ship your offered item; theirs is on the way to you."
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">Swap confirmed, {rec_name}! 🎉</h1>
<p>{intro}</p>
<div style="font-size:12px;color:#888;letter-spacing:.06em;text-transform:uppercase;margin-top:18px;">Item you'll receive</div>
{_item_card(counterpart_item)}
<div style="font-size:12px;color:#888;letter-spacing:.06em;text-transform:uppercase;margin-top:6px;">Item you're sending</div>
{_item_card(recipient_item)}
{_contact_block("Their shipping details", counterpart)}
<p>Please ship within <strong>5 working days</strong>. Once you've received the
incoming item, click below to confirm receipt:</p>
{_btn("Confirm I received the item", confirm_url)}
<p style="font-size:12px;color:#888;">When both parties confirm, the items
will swap in your closets and the listings will close automatically.</p>
"""
    return await _send(to, "Swap confirmed — please ship", _wrap(body, preheader="Both parties accepted; ship your item now."))


async def swap_denied(
    *, to: str, swapper: dict, lister: dict, listing_item: dict, offered_item: dict,
) -> dict:
    name = swapper.get("display_name") or swapper.get("name") or "there"
    lister_name = lister.get("display_name") or "the lister"
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">Hi {name},</h1>
<p>{lister_name} chose not to proceed with the swap this time. No worries —
their item is back on the marketplace and yours is still in your closet.</p>
{_item_card(listing_item)}
<p>Plenty of other listings to explore:</p>
{_btn("Browse the marketplace", f"{_APP_URL}/marketplace")}
"""
    return await _send(to, "Your swap offer was declined", _wrap(body, preheader="The lister declined; explore other listings."))


async def donation_both(
    *, to: list[str], donor: dict, recipient: dict, item: dict,
) -> dict:
    body = f"""\
<h1 style="margin:0 0 14px;font-size:22px;">A donation made it home 💚</h1>
<p>Thank you both for participating in this donation!</p>
{_item_card(item)}
{_contact_block("Donor", donor)}
{_contact_block("Recipient", recipient)}
{_btn("View in DressApp", f"{_APP_URL}/transactions")}
"""
    return await _send(to, f"Donation confirmed: {item.get('title','your item')}", _wrap(body, preheader="Donation completed — thank you both."))
