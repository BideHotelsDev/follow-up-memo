"""Sign in with Google (OpenID Connect) and the dependencies protected routes use. Adapted from bide-ecosystem.

Sign-in is invite-only: a person must already exist in `users` (seeded or added in Admin) and their email must be on
a Bide domain (Admin → Email and schedule; BIDE_DOMAINS until changed). On first sign-in their Google identity is linked by verified email; afterwards by sub.
"""

import base64
import json
import secrets
import uuid
from collections.abc import Callable
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bide_followup import clock, runtime_settings
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.errors import forbidden
from bide_followup.models import User
from bide_followup.schemas.api import DevLoginIn, ProvidersOut, UserOut

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def current_user(request: Request, session: SessionDep) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, _uuid(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(*roles: str) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise forbidden()
        return user

    return check


ADMIN = Depends(require("admin"))
OWNER_PLUS = Depends(require("owner", "admin"))


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def redirect_uri(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}"


def claims_of(id_token: str) -> dict[str, Any]:
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _sign_in(session: Session, user: User | None) -> User:
    if user is None or not user.is_active:
        raise LoginError("not_registered")
    if not runtime_settings.is_internal_email(session, user.email):
        raise LoginError("domain_not_allowed")
    user.last_sign_in_at = clock.utcnow()
    session.commit()
    return user


def _link(session: Session, sub: str, email: str | None, email_verified: bool) -> User | None:
    """The invited person behind a Google identity: by sub, or (first time) by verified email."""
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is None and email_verified and email:
        user = session.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is not None and user.google_sub not in (None, sub):
            return None  # already linked to a different Google account
        if user is not None:
            user.google_sub = sub
    return user


def google_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def exchange_google_code(code: str, callback_path: str) -> dict[str, Any]:
    """Swap an authorization code for Google's token response (ID token, and for the connect flow the API tokens)."""
    resp = httpx.post(
        settings.google_token_url,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri(callback_path),
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    body = resp.json() if resp.content else {}
    if resp.is_error or "id_token" not in body:
        raise LoginError("google_error")
    return body


def check_google_claims(claims: dict[str, Any], nonce: str) -> None:
    """The ID token comes straight from Google's token endpoint over TLS, so its signature isn't re-verified
    (OpenID Connect Core §3.1.3.7); issuer, audience and nonce are."""
    if (
        claims.get("iss") not in GOOGLE_ISSUERS
        or claims.get("aud") != settings.google_client_id
        or claims.get("nonce") != nonce
        or not claims.get("sub")
    ):
        raise LoginError("invalid_token")


def resolve_google_user(session: Session, claims: dict[str, Any], nonce: str) -> User:
    check_google_claims(claims, nonce)
    verified = claims.get("email_verified") in (True, "true")
    return _sign_in(session, _link(session, claims["sub"], claims.get("email"), verified))


def safe_next(path: str) -> str:
    # Same-site paths only: "//host" and backslashes can be read by browsers as another origin.
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else "/"


def google_authorize_url(state: str, nonce: str, callback_path: str, **extra: str) -> str:
    params = {
        "response_type": "code",
        "scope": "openid email profile",
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(callback_path),
        "state": state,
        "nonce": nonce,
        **extra,
    }
    return f"{settings.google_oauth_url}/o/oauth2/v2/auth?{urlencode(params)}"


@router.get("/google/login", include_in_schema=False)
def google_login(
    request: Request, session: SessionDep, next_path: Annotated[str, Query(alias="next")] = "/"
) -> RedirectResponse:
    if not google_configured():
        raise HTTPException(status_code=503, detail="Sign in with Google is not configured")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    request.session["oidc"] = {"state": state, "nonce": nonce, "next": safe_next(next_path)}
    extra = {"prompt": "select_account"}  # people often have several Google accounts
    domains = runtime_settings.domains(session)
    if len(domains) == 1:
        extra["hd"] = domains[0]  # a hint only; _sign_in enforces the domain
    return RedirectResponse(google_authorize_url(state, nonce, "/api/auth/google/callback", **extra))


@router.get("/google/callback", include_in_schema=False)
def google_callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    expected = request.session.pop("oidc", None)
    try:
        if error:
            raise LoginError("google_error")
        if not code or not expected or not secrets.compare_digest(state or "", expected["state"]):
            raise LoginError("invalid_state")
        body = exchange_google_code(code, "/api/auth/google/callback")
        user = resolve_google_user(session, claims_of(body["id_token"]), expected["nonce"])
    except LoginError as exc:
        return RedirectResponse(f"/?login_error={exc.code}", status_code=303)

    request.session.clear()
    request.session["user_id"] = str(user.id)
    return RedirectResponse(expected.get("next", "/"), status_code=303)


def dev_login_enabled() -> bool:
    return settings.auth_dev_login and settings.app_base_url.startswith("http://localhost")


@router.get("/providers")
def providers() -> ProvidersOut:
    """Which sign-in options the sign-in page shows."""
    return ProvidersOut(google=google_configured(), dev=dev_login_enabled())


@router.post("/dev-login", include_in_schema=False, status_code=204)
def dev_login(request: Request, session: SessionDep, body: DevLoginIn) -> None:
    if not dev_login_enabled():
        raise HTTPException(status_code=404)
    user = session.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.is_active))
    if user is None:
        raise HTTPException(status_code=403, detail="not registered")
    request.session.clear()
    request.session["user_id"] = str(user.id)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(request: Request) -> None:
    request.session.clear()
