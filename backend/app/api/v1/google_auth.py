"""Google OAuth + Calendar endpoints.

Three flows live here:

1. **Calendar connect** (existing) — an already-logged-in DressApp user clicks
   "Connect Calendar" on Profile. We mint a short-lived state JWT carrying the
   user_id, send the browser to Google with the calendar scope, and on
   callback persist tokens onto that user.

2. **Sign in with Google** (Phase T-Auth, NEW) — an *unauthenticated*
   visitor clicks "Continue with Google" on Login or Register. We mint a
   stateless state JWT (no user_id, since there is no logged-in user yet),
   redirect to Google, and on callback **find-or-create** a user by email,
   issue a DressApp JWT, and send the browser to ``/auth/callback`` on the
   frontend with the token in the URL hash fragment.

3. **Calendar status / upcoming** — small read-only endpoints used by the
   frontend Profile page and the Stylist for grounded-in-schedule advice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db.database import get_db
from app.models.schemas import User
from app.services import repos
from app.services.auth import (
    apply_admin_role,
    create_access_token,
    get_current_user,
)
from app.services.calendar_service import (
    LOGIN_SCOPES,
    SCOPES,
    calendar_service,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth/google", tags=["auth-google"])
calendar_router = APIRouter(prefix="/calendar", tags=["calendar"])

_STATE_EXPIRES_MIN = 15  # short-lived CSRF state

# Backend path used by the new sign-in flow.
#
# IMPORTANT — historic note:
#   Originally we used a *distinct* callback path
#   ``/api/v1/auth/google/login/callback`` so the two flows could co-exist
#   with different state purposes. That approach required users to register
#   *two* redirect URIs in Google Cloud Console, and OAuth clients that
#   only had the calendar URI registered started failing with
#   ``redirect_uri_mismatch`` (Google 403 page) the moment we shipped
#   sign-in-with-Google.
#
#   Both flows now share ``/api/v1/auth/google/callback`` (the URI that
#   was already registered for calendar). Dispatch happens in the
#   callback handler based on the JWT state's ``purpose`` claim. The
#   legacy ``/login/callback`` route is preserved as a thin alias so any
#   handshake mid-flight when this lands still resolves cleanly.
LOGIN_CALLBACK_PATH = "/api/v1/auth/google/callback"
LEGACY_LOGIN_CALLBACK_PATH = "/api/v1/auth/google/login/callback"

# Frontend route that finalises the sign-in handshake (parses the hash
# fragment, persists the DressApp JWT, redirects into the app).
LOGIN_FRONTEND_PATH = "/auth/callback"


# -------------------- state helpers --------------------
def _build_state(
    user_id: str | None = None,
    *,
    purpose: str = "google-oauth-link",
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "purpose": purpose,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRES_MIN),
    }
    if user_id:
        payload["sub"] = user_id
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _read_state(token: str, *, expected_purpose: str) -> dict[str, Any]:
    try:
        data = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(400, "OAuth state token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(400, "Invalid OAuth state token") from exc
    if data.get("purpose") != expected_purpose:
        raise HTTPException(400, "Invalid OAuth state payload")
    return data


# -------------------- 1) Calendar connect (existing) --------------------
@auth_router.get("/start")
async def google_oauth_start(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate the Google authorization URL for the current DressApp user."""
    if not calendar_service.enabled:
        raise HTTPException(503, "Google OAuth not configured on server")
    state = _build_state(user["id"], purpose="google-oauth-link")
    try:
        url = calendar_service.build_authorization_url(state, request=request)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"authorization_url": url, "state": state}


@auth_router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Unified callback for both Google OAuth flows.

    Dispatches based on the JWT state's ``purpose`` claim:
      * ``google-oauth-link``  → calendar connect (existing user adds Calendar)
      * ``google-oauth-login`` → sign-in / sign-up (find-or-create user)

    Sharing a single redirect URI lets the app run with **one** entry in
    Google Cloud Console regardless of which flow the user enters.
    """
    # Peek at the state to decide which branch to run. We deliberately
    # decode WITHOUT a purpose check here so a missing/malformed state
    # is handled the same way each flow used to handle it.
    purpose = None
    if state:
        try:
            unverified = jwt.decode(
                state,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            purpose = unverified.get("purpose")
        except Exception:  # noqa: BLE001
            purpose = None

    if purpose == "google-oauth-login":
        return await _handle_login_callback(request, code, state, error)
    # Default branch: calendar-link (back-compat with any state minted
    # by the original ``/callback`` handler).
    return await _handle_calendar_link_callback(request, code, state, error)


async def _handle_calendar_link_callback(
    request: Request,
    code: str | None,
    state: str | None,
    error: str | None,
) -> RedirectResponse:
    """Calendar-connect branch (existing logic, extracted verbatim)."""
    redirect_base = calendar_service.resolve_post_login_redirect(request)

    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(f"{redirect_base}?calendar=error&reason={error}")
    if not code or not state:
        return RedirectResponse(f"{redirect_base}?calendar=error&reason=missing_params")

    try:
        data = _read_state(state, expected_purpose="google-oauth-link")
    except HTTPException as exc:
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason={exc.detail.replace(' ', '_')}"
        )
    user_id = data.get("sub")
    if not user_id:
        return RedirectResponse(f"{redirect_base}?calendar=error&reason=missing_user")

    try:
        tokens = await calendar_service.exchange_code(code, request=request)
    except Exception:  # noqa: BLE001
        logger.exception("Google token exchange failed")
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason=token_exchange_failed"
        )

    try:
        await calendar_service.persist_tokens_for_user(user_id, tokens)
    except Exception:  # noqa: BLE001
        logger.exception("Persisting Google tokens failed")
        return RedirectResponse(
            f"{redirect_base}?calendar=error&reason=persist_failed"
        )

    return RedirectResponse(f"{redirect_base}?calendar=connected")


@auth_router.post("/disconnect")
async def google_oauth_disconnect(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    await calendar_service.disconnect_user(user["id"])
    return {"status": "disconnected"}


# -------------------- 2) Sign in / Sign up with Google (NEW) --------------------
def _frontend_origin(request: Request) -> str:
    """Resolve the public frontend origin for the post-login redirect.

    Reuses the same env override / X-Forwarded headers logic the calendar
    flow relies on, so this works on preview, staging, prod and any custom
    domain without .env edits.
    """
    if settings.GOOGLE_OAUTH_POST_LOGIN_REDIRECT:
        # Strip path component if present — we want just origin here.
        from urllib.parse import urlparse

        parsed = urlparse(settings.GOOGLE_OAUTH_POST_LOGIN_REDIRECT)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    headers = request.headers
    scheme = headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = (
        headers.get("x-forwarded-host")
        or headers.get("host")
        or request.url.netloc
    )
    host = (host or "").split(",")[0].strip()
    return f"{scheme}://{host}" if host else ""


def _login_error_redirect(origin: str, reason: str) -> RedirectResponse:
    target = f"{origin}{LOGIN_FRONTEND_PATH}#error={reason}"
    return RedirectResponse(target)


@auth_router.get("/login/start")
async def google_login_start(
    request: Request,
    with_calendar: bool = Query(
        default=False,
        description="When true, also requests the calendar.readonly scope so the user lands logged-in *and* calendar-connected in a single consent.",
    ),
    next: str | None = Query(  # noqa: A002 — query name is intentional
        default=None,
        description="Optional frontend path to redirect to after sign-in. Only relative paths are honoured.",
    ),
) -> dict[str, Any]:
    """Public endpoint that returns the Google authorization URL for the
    *sign-in / sign-up* flow. No DressApp credentials required.
    """
    if not calendar_service.enabled:
        raise HTTPException(503, "Google OAuth not configured on server")

    # Sanitize ``next`` — only allow relative paths to prevent open-redirect.
    safe_next = None
    if next and next.startswith("/") and not next.startswith("//"):
        safe_next = next

    state = _build_state(
        purpose="google-oauth-login",
        extra={
            "with_calendar": bool(with_calendar),
            "next": safe_next,
        },
    )

    scopes = SCOPES if with_calendar else LOGIN_SCOPES
    try:
        url = calendar_service.build_authorization_url(
            state,
            request=request,
            scopes=scopes,
            callback_path=LOGIN_CALLBACK_PATH,
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"authorization_url": url, "with_calendar": bool(with_calendar)}


@auth_router.get("/login/diag")
async def google_login_diag(request: Request) -> dict[str, Any]:
    """Read-only diagnostic that returns the *exact* redirect_uri the
    backend will send to Google for the sign-in flow. Use this to verify
    the URI registered in your Google Cloud Console matches byte-for-byte.

    Safe to expose: no secrets are leaked, only the public client_id and
    the request-derived origin.
    """
    redirect_uri = calendar_service.resolve_redirect_uri(
        request, callback_path=LOGIN_CALLBACK_PATH
    )
    calendar_redirect_uri = calendar_service.resolve_redirect_uri(request)
    return {
        "enabled": calendar_service.enabled,
        "client_id_present": bool(calendar_service.client_id),
        "client_id_tail": (
            (calendar_service.client_id or "")[-12:]
            if calendar_service.client_id
            else None
        ),
        "login_redirect_uri": redirect_uri,
        "calendar_redirect_uri": calendar_redirect_uri,
        "headers_seen": {
            "host": request.headers.get("host"),
            "x-forwarded-host": request.headers.get("x-forwarded-host"),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
        },
    }


@auth_router.get("/login/callback")
async def google_login_callback_legacy(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Legacy alias kept ONLY for users mid-flow when the unified-callback
    refactor lands. New starts always go through ``/callback``. Safe to
    remove after one full release cycle.

    Crucially, we forward the **legacy** callback path to ``exchange_code``
    so Google's token endpoint sees the same ``redirect_uri`` the
    authorize step used (otherwise Google rejects with
    ``invalid_grant: redirect_uri mismatch``).
    """
    return await _handle_login_callback(
        request, code, state, error,
        callback_path=LEGACY_LOGIN_CALLBACK_PATH,
    )


async def _handle_login_callback(
    request: Request,
    code: str | None,
    state: str | None,
    error: str | None,
    *,
    callback_path: str = LOGIN_CALLBACK_PATH,
) -> RedirectResponse:
    """Handle Google's redirect for the *sign-in / sign-up* flow.

    On success: find-or-create user by email, optionally persist calendar
    tokens, mint a DressApp JWT, redirect to the frontend with the token
    in the URL hash fragment (so it never hits any access log).
    """
    origin = _frontend_origin(request) or ""

    if error:
        logger.warning("Google sign-in OAuth error: %s", error)
        return _login_error_redirect(origin, error)
    if not code or not state:
        return _login_error_redirect(origin, "missing_params")

    try:
        state_data = _read_state(state, expected_purpose="google-oauth-login")
    except HTTPException as exc:
        return _login_error_redirect(origin, exc.detail.replace(" ", "_"))

    with_calendar = bool(state_data.get("with_calendar"))
    next_path = state_data.get("next") or "/home"

    # 1) Exchange the auth code.
    try:
        tokens = await calendar_service.exchange_code(
            code, request=request, callback_path=callback_path
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Google sign-in token exchange failed")
        # Surface a compact reason so the user can see it in the URL hash
        # without having to grep backend logs. We URL-quote-plus to avoid
        # breaking the fragment parser on ``=`` / ``&`` characters.
        from urllib.parse import quote_plus

        reason = quote_plus(f"token_exchange_failed: {str(exc)[:160]}")
        return RedirectResponse(f"{origin}{LOGIN_FRONTEND_PATH}#error={reason}")

    access_token = tokens.get("access_token")
    if not access_token:
        return _login_error_redirect(origin, "no_access_token")

    # 2) Fetch userinfo (email is the join key).
    try:
        userinfo = await calendar_service.fetch_userinfo(access_token)
    except Exception:  # noqa: BLE001
        logger.exception("Google sign-in userinfo fetch failed")
        return _login_error_redirect(origin, "userinfo_failed")

    email = (userinfo.get("email") or "").lower()
    if not email:
        return _login_error_redirect(origin, "no_email")
    if not userinfo.get("verified_email", True):
        # Most Google accounts are verified; reject unverified to prevent
        # account-takeover via email collision.
        return _login_error_redirect(origin, "email_unverified")

    db = get_db()
    existing = await db.users.find_one({"email": email}, {"_id": 0})

    # 3) Find-or-create the user (auto-link by email per decision 2a).
    if existing:
        user_doc = existing
        patch: dict[str, Any] = {}
        # Autofill profile fields that are still empty — mirrors the same
        # logic used by ``calendar_service.persist_tokens_for_user`` so the
        # behaviour is consistent regardless of which path is taken.
        if userinfo.get("given_name") and not user_doc.get("first_name"):
            patch["first_name"] = userinfo["given_name"]
        if userinfo.get("family_name") and not user_doc.get("last_name"):
            patch["last_name"] = userinfo["family_name"]
        if userinfo.get("name") and not user_doc.get("display_name"):
            patch["display_name"] = userinfo["name"]
        if userinfo.get("picture") and not user_doc.get("avatar_url"):
            patch["avatar_url"] = userinfo["picture"]
        if userinfo.get("locale") and not user_doc.get("locale"):
            patch["locale"] = userinfo["locale"]
        # Re-apply admin allow-list on every Google login — same idempotent
        # behaviour as email/password login.
        new_roles = apply_admin_role(user_doc.get("roles"), email)
        if set(new_roles) != set(user_doc.get("roles") or []):
            patch["roles"] = new_roles
        if patch:
            patch["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.users.update_one({"id": user_doc["id"]}, {"$set": patch})
            user_doc.update(patch)
        logger.info("google sign-in: linked existing user email=%s", email)
    else:
        new_user = User(
            email=email,
            password_hash=None,
            display_name=userinfo.get("name")
            or userinfo.get("given_name")
            or email.split("@")[0],
            avatar_url=userinfo.get("picture"),
            first_name=userinfo.get("given_name"),
            last_name=userinfo.get("family_name"),
            locale=userinfo.get("locale") or "en-US",
        )
        user_doc = new_user.model_dump()
        user_doc["roles"] = apply_admin_role(user_doc.get("roles"), email)
        await repos.insert(db.users, user_doc)
        logger.info("google sign-in: created new user email=%s id=%s", email, new_user.id)

    # 4) Optionally persist calendar tokens (only if the user opted in).
    if with_calendar:
        try:
            await calendar_service.persist_tokens_for_user(user_doc["id"], tokens)
        except Exception:  # noqa: BLE001
            # Don't fail the whole sign-in if calendar persistence trips —
            # surface a soft warning via the URL hash so the frontend can
            # show a toast.
            logger.exception("Calendar token persist failed during sign-in")
            jwt_token = create_access_token(
                user_doc["id"], {"email": user_doc["email"]}
            )
            params = urlencode(
                {
                    "token": jwt_token,
                    "next": next_path,
                    "warning": "calendar_persist_failed",
                }
            )
            return RedirectResponse(f"{origin}{LOGIN_FRONTEND_PATH}#{params}")

    # 5) Mint our own JWT and hand it back to the frontend in the hash.
    jwt_token = create_access_token(
        user_doc["id"], {"email": user_doc["email"]}
    )
    params = urlencode({"token": jwt_token, "next": next_path})
    return RedirectResponse(f"{origin}{LOGIN_FRONTEND_PATH}#{params}")


# -------------------- 3) calendar routes --------------------
@calendar_router.get("/status")
async def calendar_status(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    tokens = (user or {}).get("google_calendar_tokens") or {}
    return {
        "connected": bool(tokens.get("refresh_token")),
        "google_email": tokens.get("google_email"),
        "connected_at": tokens.get("connected_at"),
        "scope": tokens.get("scope"),
    }


@calendar_router.get("/upcoming")
async def calendar_upcoming(
    hours_ahead: int = Query(default=48, ge=1, le=168),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    events = await calendar_service.get_events_for_user(user, hours_ahead=hours_ahead)
    return {"events": events, "count": len(events)}
