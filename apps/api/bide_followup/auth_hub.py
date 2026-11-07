"""Sign in with Bide: the app as an OpenID Connect client of Bide Hub (bide-hub docs/integrating.md).

On when BIDE_HUB_ISSUER, BIDE_HUB_CLIENT_ID and BIDE_HUB_CLIENT_SECRET are all set (auth.hub_configured). The Hub
says who someone is and that they may open the app; the app's own rules still apply after that (auth._sign_in:
invite-only, Bide domains). The Hub identity is linked to the invited person by sub, or the first time by email.

Sessions stay the app's signed cookie, carrying the Hub `sid`. When someone signs out of the Hub (here or in another
system) the Hub posts a logout token to /backchannel-logout, which records it in `hub_logouts`; auth.current_user
then refuses the matching sessions.
"""

import base64
import hashlib
import secrets
from datetime import timedelta
from functools import cache
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bide_followup import clock
from bide_followup.auth import LoginError, _sign_in, hub_configured, redirect_uri, safe_next, start_session
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.models import HubLogout, User

CALLBACK_PATH = "/api/auth/bide/callback"
BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout"
# The Hub's answers on the callback that mean "you can't open this app" rather than "something broke".
DENIED_ERRORS = ("access_denied", "login_required")

router = APIRouter(prefix="/api/auth/bide", tags=["auth"])


def issuer() -> str:
    return settings.bide_hub_issuer.rstrip("/")


@cache
def _discovery(iss: str) -> dict[str, Any]:
    resp = httpx.get(f"{iss}/.well-known/openid-configuration", timeout=10)
    resp.raise_for_status()
    return resp.json()


def discovery() -> dict[str, Any]:
    """The Hub's endpoints, fetched once per process."""
    try:
        return _discovery(issuer())
    except (httpx.HTTPError, ValueError) as exc:
        raise LoginError("hub_error") from exc


@cache
def _jwks(uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(uri, cache_keys=True)


def verify(token: str) -> dict[str, Any]:
    """A JWT signed by the Hub for this app: RS256 against the Hub's JWKS, issuer, audience and expiry."""
    try:
        key = _jwks(discovery()["jwks_uri"]).get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.bide_hub_client_id,
            issuer=issuer(),
            options={"require": ["iss", "aud", "exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise LoginError("invalid_token") from exc


def code_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    try:
        resp = httpx.post(
            discovery()["token_endpoint"],
            auth=(settings.bide_hub_client_id, settings.bide_hub_client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(CALLBACK_PATH),
                "code_verifier": verifier,
            },
            timeout=15,
        )
        body = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise LoginError("hub_error") from exc
    if resp.is_error or "id_token" not in body:
        raise LoginError("hub_error")
    return body


def _link(session: Session, sub: str, email: str | None) -> User | None:
    """The invited person behind a Hub identity: by sub, or (first time) by email. The Hub only sends verified
    emails."""
    user = session.scalar(select(User).where(User.bide_hub_sub == sub))
    if user is None and email:
        user = session.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is not None and user.bide_hub_sub not in (None, sub):
            return None  # already linked to a different Hub identity
        if user is not None:
            user.bide_hub_sub = sub
    return user


def resolve_user(session: Session, claims: dict[str, Any], nonce: str) -> User:
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise LoginError("invalid_token")
    return _sign_in(session, _link(session, claims["sub"], claims.get("email")))


def _require_hub() -> None:
    if not hub_configured():
        raise HTTPException(status_code=404)


@router.get("/login", include_in_schema=False)
def login(request: Request, next_path: Annotated[str, Query(alias="next")] = "/") -> RedirectResponse:
    _require_hub()
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    request.session["bide_hub"] = {"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next_path)}
    try:
        endpoint = discovery()["authorization_endpoint"]
    except LoginError as exc:
        return RedirectResponse(f"/?login_error={exc.code}", status_code=303)
    params = {
        "response_type": "code",
        "client_id": settings.bide_hub_client_id,
        "redirect_uri": redirect_uri(CALLBACK_PATH),
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{endpoint}?{urlencode(params)}")


@router.get("/callback", include_in_schema=False)
def callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    _require_hub()
    expected = request.session.pop("bide_hub", None)
    try:
        if not expected or not secrets.compare_digest(state or "", expected["state"]):
            raise LoginError("invalid_state")
        if error:
            raise LoginError("hub_denied" if error in DENIED_ERRORS else "hub_error")
        if not code:
            raise LoginError("invalid_state")
        body = exchange_code(code, expected["verifier"])
        claims = verify(body["id_token"])
        user = resolve_user(session, claims, expected["nonce"])
    except LoginError as exc:
        return RedirectResponse(f"/?login_error={exc.code}", status_code=303)

    start_session(request, user, hub_sid=claims.get("sid"))
    return RedirectResponse(expected.get("next", "/"), status_code=303)


@router.post("/backchannel-logout", include_in_schema=False)
def backchannel_logout(session: SessionDep, logout_token: Annotated[str, Form()]) -> None:
    """The Hub, server to server, when someone signs out anywhere, signs out everywhere or is switched off."""
    _require_hub()
    try:
        claims = verify(logout_token)
    except LoginError as exc:
        raise HTTPException(status_code=400, detail="invalid logout token") from exc
    events = claims.get("events")
    if "nonce" in claims or not isinstance(events, dict) or BACKCHANNEL_EVENT not in events:
        raise HTTPException(status_code=400, detail="invalid logout token")
    # Sessions last SESSION_DAYS at most, so older records can't match anything any more.
    session.execute(
        delete(HubLogout).where(HubLogout.created_at < clock.utcnow() - timedelta(days=settings.session_days))
    )
    session.add(HubLogout(sid=claims.get("sid"), sub=claims["sub"]))
    session.commit()
