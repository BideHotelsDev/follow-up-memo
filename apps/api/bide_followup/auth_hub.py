"""Sign in with Bide: the app as an OpenID Connect client of Bide Hub (bide-hub docs/integrating.md).

On when BIDE_HUB_ISSUER, BIDE_HUB_CLIENT_ID and BIDE_HUB_CLIENT_SECRET are all set (auth.hub_configured). The Hub
says who someone is and that they may open the app; the app's own rules still apply after that (auth._sign_in:
invite-only, Bide domains). The Hub identity is linked to the invited person by sub, or the first time by email.

Talking to the Hub (discovery, keys, PKCE, the code exchange, checking every token) is the shared bide-hub-client,
vendored under _vendor/ (don't edit it here: change it in bide-hub and sync). This module keeps what is the app's own:
which user a Hub identity is, its session, and what a logout ends.

Sessions stay the app's signed cookie, carrying the Hub `sid`. When someone signs out of the Hub (here or in another
system) the Hub posts a logout token to /backchannel-logout, which records it in `hub_logouts`; auth.current_user
then refuses the matching sessions.
"""

from datetime import timedelta
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bide_followup import clock
from bide_followup._vendor.bide_hub_client import (
    ACCOUNT_DISABLED_EVENT,
    BACKCHANNEL_EVENT,
    HubClient,
    HubDenied,
    HubError,
    Identity,
    InvalidToken,
    PendingLogin,
)
from bide_followup.auth import LoginError, _sign_in, hub_configured, redirect_uri, safe_next, start_session
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.models import AuditLog, HubLogout, User

__all__ = ["ACCOUNT_DISABLED_EVENT", "BACKCHANNEL_EVENT", "hub", "router"]

CALLBACK_PATH = "/api/auth/bide/callback"
PENDING = "bide_hub"  # the session key holding the sign-in in progress

router = APIRouter(prefix="/api/auth/bide", tags=["auth"])


@cache
def _client(issuer: str, client_id: str, client_secret: str) -> HubClient:
    # The app's clock (tests freeze it), so a logout's time is capped at the same "now" the sessions are dated by.
    return HubClient(issuer, client_id, client_secret, now=lambda: clock.utcnow().timestamp())


def hub() -> HubClient:
    """The Hub client for the current settings (one per configuration, so its caches are shared)."""
    return _client(settings.bide_hub_issuer, settings.bide_hub_client_id, settings.bide_hub_client_secret)


def _login_error(exc: HubError) -> LoginError:
    """The sign-in page's message for what went wrong (the codes it already knows)."""
    if isinstance(exc, HubDenied):
        return LoginError("hub_denied" if exc.no_access else "hub_error")
    return LoginError({"invalid_token": "invalid_token", "invalid_state": "invalid_state"}.get(exc.code, "hub_error"))


def _link(session: Session, sub: str, email: str | None) -> User | None:
    """The invited person behind a Hub identity: by sub, or (first time) by email. `email` is only set when the Hub
    has verified it (bide-hub-client's Identity.email)."""
    user = session.scalar(select(User).where(User.bide_hub_sub == sub))
    if user is None and email:
        user = session.scalar(select(User).where(func.lower(User.email) == email))
        if user is not None and user.bide_hub_sub not in (None, sub):
            return None  # already linked to a different Hub identity
        if user is not None:
            user.bide_hub_sub = sub
    return user


def resolve_user(session: Session, identity: Identity) -> User:
    return _sign_in(session, _link(session, identity.sub, identity.email))


def _require_hub() -> None:
    if not hub_configured():
        raise HTTPException(status_code=404)


@router.get("/login", include_in_schema=False)
def login(request: Request, next_path: Annotated[str, Query(alias="next")] = "/") -> RedirectResponse:
    _require_hub()
    try:
        url, pending = hub().start_login(redirect_uri(CALLBACK_PATH), safe_next(next_path))
    except HubError as exc:
        return RedirectResponse(f"/?login_error={_login_error(exc).code}", status_code=303)
    request.session[PENDING] = pending.to_dict()
    return RedirectResponse(url)


@router.get("/callback", include_in_schema=False)
def callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    _require_hub()
    pending = PendingLogin.from_dict(request.session.pop(PENDING, None))
    try:
        identity = hub().finish_login(pending, redirect_uri(CALLBACK_PATH), state, code, error)
        user = resolve_user(session, identity)
    except HubError as exc:
        return RedirectResponse(f"/?login_error={_login_error(exc).code}", status_code=303)
    except LoginError as exc:
        return RedirectResponse(f"/?login_error={exc.code}", status_code=303)

    start_session(request, user, hub_sid=identity.sid)
    return RedirectResponse(pending.next if pending else "/", status_code=303)


@router.post("/backchannel-logout", include_in_schema=False)
def backchannel_logout(session: SessionDep, logout_token: Annotated[str, Form()]) -> None:
    """The Hub, server to server, when someone signs out anywhere, signs out everywhere or is switched off. Switched
    off, the token also carries the account-disabled event: the person linked to that Hub identity (by sub only, never
    by email) is switched off here too, with an audit entry. Switching them back on is an Admin's job in the app."""
    _require_hub()
    try:
        logout = hub().verify_logout_token(logout_token)
    except InvalidToken as exc:
        raise HTTPException(status_code=400, detail="invalid logout token") from exc
    except HubError as exc:  # the Hub's keys couldn't be fetched: not a 2xx, so the Hub tries again later
        raise HTTPException(status_code=503, detail="couldn't check the logout token") from exc
    # Sessions last SESSION_DAYS at most, so older records can't match anything any more.
    session.execute(
        delete(HubLogout).where(HubLogout.created_at < clock.utcnow() - timedelta(days=settings.session_days))
    )
    # Dated when the sign-out happened, not when this (possibly retried) delivery arrived, so a late delivery doesn't
    # end sessions the person started after signing out.
    session.add(HubLogout(sid=logout.sid, sub=logout.sub, created_at=logout.logout_at))
    if logout.disabled:
        user = session.scalar(select(User).where(User.bide_hub_sub == logout.sub))
        if user is not None and user.is_active:
            user.is_active = False
            session.add(
                AuditLog(
                    user_id=None,
                    entity="user",
                    entity_id=user.id,
                    action="update",
                    before={"is_active": True},
                    after={"is_active": False, "reason": "bide_hub_account_disabled"},
                )
            )
    session.commit()
