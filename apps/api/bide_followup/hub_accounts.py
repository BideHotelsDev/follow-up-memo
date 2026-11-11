"""Accounts managed by Bide Hub: the Hub says who has an account in Follow-up, and with which role.

The contract is the Hub's docs/integrating.md ("Accounts managed by the Hub"). Off unless Sign in with Bide is on and
BIDE_HUB_MANAGES_ACCOUNTS is set, so the Hub can't take over the accounts here until an operator has said it may.

    GET  /api/auth/bide/provisioning/catalog            the roles, for the Hub's People screen
    GET  /api/auth/bide/provisioning/users              the accounts here, for the Hub's one-time import
    PUT  /api/auth/bide/provisioning/users/{sub}        make this person's account match the Hub
    POST /api/auth/bide/provisioning/users/{sub}/check  would that PUT be accepted? changes nothing

Every call carries a short-lived token the Hub signs with its sign-in key; bide-hub-client checks it (purpose, method,
the full address built from APP_BASE_URL, a hash of the body).

The Hub saves a change first and then delivers it, repeating the PUT until it gets a 2xx. So:

- A PUT refuses only what it can't apply: no role or more than one (Follow-up gives each person one), an unknown role,
  an email that belongs to another Hub person. It may arrive more than once; it simply makes the account match.
- `active: false` is never refused, and never creates an account. If it leaves nobody in charge (no active owner or
  admin), the Hub Admin is warned and the fix is made in the Hub.
- "Someone stays in charge" lives in the check, which the Hub asks before saving anything else: demoting the last owner
  or admin is refused there; a PUT carrying a change the Hub already saved applies it and warns.

What stays Follow-up's own: Slack IDs and ownership areas (still edited under Admin → People), and what each role may do.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bide_followup import auth_hub, clock
from bide_followup._vendor.bide_hub_client import HubError, InvalidToken
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.models import AuditLog, User

log = logging.getLogger(__name__)

PATH = "/api/auth/bide/provisioning"
FEATURES = ["check"]
IN_CHARGE = ("owner", "admin")
ROLES = [
    {"key": "owner", "name": "Owner", "description": "Runs Follow-up: approves follow-ups and manages people."},
    {"key": "admin", "name": "Admin", "description": "Manages people, settings and connections."},
    {"key": "member", "name": "Member", "description": "Sees and answers their own follow-ups."},
]
NO_STORE = {"Cache-Control": "no-store"}


class Refused(Exception):
    """The Hub's request can't be carried out. The message is shown to the Hub Admin."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def managed() -> bool:
    return settings.accounts_managed_by_hub


# --- what the Hub reads ---------------------------------------------------------------------------------------------


def catalog() -> dict[str, Any]:
    return {
        "roles": [{**r, "scoped": False} for r in ROLES],
        "scopes": [],
        "unscoped_label": "All of Follow-up",
        # One role per person here: the Hub's People screen offers a single one.
        "max_assignments": 1,
        "features": FEATURES,
    }


def accounts(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "email": u.email,
            "name": u.name,
            "active": u.is_active,
            "sub": u.bide_hub_sub,
            "assignments": [{"role": u.role, "scope": None}],
        }
        for u in session.scalars(select(User).order_by(User.email))
    ]


# --- what the Hub changes -------------------------------------------------------------------------------------------


def _role(raw: Any) -> str:
    roles = {str(a.get("role") or "") for a in raw or [] if isinstance(a, dict)}
    if not roles:
        raise Refused("pick a role for Follow-up (Owner, Admin or Member).", 422)
    if len(roles) > 1:
        raise Refused("Follow-up gives each person one role: pick just one.", 422)
    (role,) = roles
    if role not in {r["key"] for r in ROLES}:
        raise Refused(f"there is no role '{role}' in Follow-up.", 422)
    return role


def _find(session: Session, sub: str, email: str) -> User | None:
    user = session.scalar(select(User).where(User.bide_hub_sub == sub))
    if user is not None:
        return user
    user = session.scalar(select(User).where(func.lower(User.email) == email))
    if user is not None and user.bide_hub_sub and user.bide_hub_sub != sub:
        raise Refused(f"{email} belongs to a different Hub person in Follow-up.")
    return user


def _in_charge(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User).where(User.is_active, User.role.in_(IN_CHARGE))) or 0


def _nobody_in_charge(user: User) -> str:
    return (
        f"{user.name or user.email} was the last active owner or admin in Follow-up. Until you give someone the Owner "
        "or Admin role in Bide Hub, nobody can approve follow-ups or manage people there."
    )


def _audit(session: Session, user: User, before: dict | None, after: dict) -> None:
    session.add(
        AuditLog(
            user_id=None,
            entity="user",
            entity_id=user.id,
            action="update",
            before=before,
            after={**after, "by": "bide_hub"},
        )
    )


def _apply(session: Session, sub: str, payload: dict, *, checking: bool) -> tuple[User | None, list[str]]:
    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise Refused("the Hub sent no email.", 422)
    active = bool(payload.get("active"))
    warnings: list[str] = []
    had = _in_charge(session)
    try:
        user = _find(session, sub, email)
    except Refused:
        if active:
            raise
        return None, warnings  # the address is someone else's here, and this person has nothing to switch off

    if not active:
        # No access at the Hub: switch the account off if there is one, never make one. Never refused.
        if user is None or not user.is_active:
            return user, warnings
        user.is_active = False
        user.sessions_valid_after = clock.utcnow()  # switching them back on later doesn't revive old sessions
        session.flush()
        if had and not _in_charge(session):
            warnings.append(_nobody_in_charge(user))
        _audit(session, user, {"is_active": True}, {"is_active": False})
        session.flush()
        return user, warnings

    role = _role(payload.get("assignments"))
    if user is None:
        user = User(email=email, name=str(payload.get("name") or "").strip()[:120] or email, role=role)
        session.add(user)
        before = None
    else:
        before = {"email": user.email, "name": user.name, "role": user.role, "is_active": user.is_active}
        if user.email.lower() != email:
            clash = session.scalar(select(User.id).where(func.lower(User.email) == email, User.id != user.id))
            if clash:
                raise Refused(f"{email} is already another account in Follow-up.")
            user.email = email
        name = str(payload.get("name") or "").strip()
        if name:
            user.name = name[:120]
        if not user.is_active:
            user.sessions_valid_after = clock.utcnow()
        user.role = role
        user.is_active = True
    user.bide_hub_sub = sub
    session.flush()
    if had and not _in_charge(session):
        # This change removes the last owner or admin. Asked before the Hub saves: refused there. A PUT carries a change
        # the Hub has already saved, so it is applied, and the Hub is where someone is put back in charge.
        if checking:
            raise Refused("Follow-up needs at least one active owner or admin: give someone else that role first.")
        warnings.append(_nobody_in_charge(user))
    elif not _in_charge(session):
        warnings.append("Nobody is an active owner or admin in Follow-up: give someone that role in Bide Hub.")
    _audit(session, user, before, {"email": user.email, "name": user.name, "role": user.role, "is_active": True})
    session.flush()
    return user, warnings


def apply(session: Session, sub: str, payload: dict) -> User | None:
    """Make the account for this Hub person match `payload`. Commits; on Refused nothing of it is kept."""
    try:
        user, warnings = _apply(session, sub, payload, checking=False)
    except Exception:
        session.rollback()
        raise
    session.commit()
    for warning in warnings:
        log.warning("Bide Hub push for %s: %s", sub, warning)
    return user


def check(session: Session, sub: str, payload: dict) -> list[str]:
    """Would `apply` accept this? Runs it and throws the result away, so the answer is exactly the PUT's."""
    try:
        _, warnings = _apply(session, sub, payload, checking=True)
    finally:
        session.rollback()
    return warnings


# --- the routes -----------------------------------------------------------------------------------------------------


def _require_managed() -> None:
    if not managed():
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(prefix=PATH, tags=["auth"], include_in_schema=False, dependencies=[Depends(_require_managed)])


async def _verified(request: Request, path: str) -> bytes:
    """The raw body, once the Hub's token for exactly this call checks out. Async only to read the body; the check (it
    may fetch the Hub's keys) runs in the thread pool."""
    body = await request.body()
    url = f"{settings.app_base_url.rstrip('/')}{PATH}{path}"
    try:
        await run_in_threadpool(
            auth_hub.hub().verify_provisioning_request, request.headers.get("authorization"), request.method, url, body
        )
    except InvalidToken as exc:
        log.warning("Bide Hub provisioning refused: %s", exc)
        raise HTTPException(status_code=401, detail="invalid token") from exc
    except HubError as exc:  # the Hub's keys couldn't be fetched: a 5xx, which the Hub retries
        raise HTTPException(status_code=503, detail="can't check the token") from exc
    return body


def _payload(sub: str, body: bytes) -> dict:
    try:
        payload = json.loads(body or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="not JSON") from exc
    if not isinstance(payload, dict) or len(sub) > 64:
        raise HTTPException(status_code=422, detail="bad request")
    return payload


@router.get("/catalog")
async def get_catalog(request: Request) -> JSONResponse:
    await _verified(request, "/catalog")
    return JSONResponse(catalog(), headers=NO_STORE)


@router.get("/users")
async def get_users(request: Request, session: SessionDep) -> JSONResponse:
    await _verified(request, "/users")
    return JSONResponse(await run_in_threadpool(accounts, session), headers=NO_STORE)


@router.post("/users/{sub}/check")
async def check_user(sub: str, request: Request, session: SessionDep) -> JSONResponse:
    payload = _payload(sub, await _verified(request, f"/users/{sub}/check"))
    try:
        warnings = await run_in_threadpool(check, session, sub, payload)
    except Refused as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "warnings": warnings}, headers=NO_STORE)


@router.put("/users/{sub}")
async def put_user(sub: str, request: Request, session: SessionDep) -> JSONResponse:
    payload = _payload(sub, await _verified(request, f"/users/{sub}"))
    try:
        user = await run_in_threadpool(apply, session, sub, payload)
    except Refused as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    body = {"id": str(user.id), "active": user.is_active} if user else {"id": None, "active": False}
    return JSONResponse(body, headers=NO_STORE)


__all__ = ["Refused", "accounts", "apply", "catalog", "check", "managed", "router"]
