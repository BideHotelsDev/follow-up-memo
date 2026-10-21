"""Connecting David's Google account and installing the Slack bot (Admin, once). PRD §8."""

import secrets
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from bide_followup import auth, runtime_settings
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.integrations import google_oauth, llm, slack
from bide_followup.models import LlmJob, User
from bide_followup.routers import service
from bide_followup.schemas.api import ClaudeModeIn, ClaudeStatusOut, ConnectionOut, ConnectionsOut, RoutineTokenOut

router = APIRouter(prefix="/api", tags=["connections"])

GOOGLE_CONNECT_CALLBACK = "/api/auth/google/connect/callback"
SLACK_INSTALL_CALLBACK = "/api/auth/slack/callback"
DONE = "/admin/connections"

# David (owner) and Kyle (admin) both run Admin.
Admin = Annotated[User, Depends(auth.require("owner", "admin"))]


@router.get("/auth/google/connect", include_in_schema=False)
def google_connect(request: Request, _: Admin, login_hint: str = "") -> RedirectResponse:
    if not auth.google_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    request.session["connect"] = {"state": state, "nonce": nonce}
    url = auth.google_authorize_url(
        state,
        nonce,
        GOOGLE_CONNECT_CALLBACK,
        scope=" ".join(google_oauth.SCOPES),
        access_type="offline",
        prompt="consent",  # without consent Google returns no refresh token on a reconnect
        include_granted_scopes="true",
        **({"login_hint": login_hint} if login_hint else {}),
    )
    return RedirectResponse(url)


@router.get("/auth/google/connect/callback", include_in_schema=False)
def google_connect_callback(
    request: Request,
    session: SessionDep,
    _: Admin,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    expected = request.session.pop("connect", None)
    try:
        if error:
            raise auth.LoginError("google_error")
        if not code or not expected or not secrets.compare_digest(state or "", expected["state"]):
            raise auth.LoginError("invalid_state")
        body = auth.exchange_google_code(code, GOOGLE_CONNECT_CALLBACK)
        claims = auth.claims_of(body["id_token"])
        auth.check_google_claims(claims, expected["nonce"])
        missing = set(google_oauth.SCOPES) - {"openid", "email"} - set(body.get("scope", "").split())
        if missing:
            raise auth.LoginError("scopes_missing")
        google_oauth.save(session, claims.get("email", ""), body)
    except (auth.LoginError, google_oauth.GoogleAuthError) as exc:
        code_ = exc.code if isinstance(exc, auth.LoginError) else "no_refresh_token"
        return RedirectResponse(f"{DONE}?error={code_}", status_code=303)
    return RedirectResponse(f"{DONE}?connected=google", status_code=303)


@router.get("/auth/slack/install", include_in_schema=False)
def slack_install(request: Request, _: Admin) -> RedirectResponse:
    if not (settings.slack_client_id and settings.slack_client_secret):
        raise HTTPException(status_code=503, detail="The Slack app is not configured")
    state = secrets.token_urlsafe(24)
    request.session["slack_install"] = state
    params = {
        "client_id": settings.slack_client_id,
        "scope": ",".join(slack.BOT_SCOPES),
        "redirect_uri": auth.redirect_uri(SLACK_INSTALL_CALLBACK),
        "state": state,
    }
    return RedirectResponse(f"{settings.slack_oauth_url}?{urlencode(params)}")


@router.get("/auth/slack/callback", include_in_schema=False)
def slack_callback(
    request: Request,
    session: SessionDep,
    _: Admin,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    expected = request.session.pop("slack_install", None)
    if error or not code or not expected or not secrets.compare_digest(state or "", expected):
        return RedirectResponse(f"{DONE}?error=slack_error", status_code=303)
    resp = httpx.post(
        f"{settings.slack_api_url}/oauth.v2.access",
        data={
            "code": code,
            "client_id": settings.slack_client_id,
            "client_secret": settings.slack_client_secret,
            "redirect_uri": auth.redirect_uri(SLACK_INSTALL_CALLBACK),
        },
        timeout=15,
    )
    body = resp.json() if resp.content else {}
    if not body.get("ok"):
        return RedirectResponse(f"{DONE}?error=slack_error", status_code=303)
    slack.save(session, body)
    return RedirectResponse(f"{DONE}?connected=slack", status_code=303)


@router.get("/admin/connections")
def connections(session: SessionDep, _: Admin) -> ConnectionsOut:
    def out(row) -> ConnectionOut | None:
        return ConnectionOut.model_validate(row) if row else None

    return ConnectionsOut(google=out(google_oauth.integration(session)), slack=out(slack.integration(session)))


ROUTINE_PROMPT = Path(__file__).parent.parent / "prompts" / "routine.md"
# Hourly in working hours, weekdays (UTC: 08:05–20:05 UK summer time). Routines run at most hourly.
ROUTINE_SCHEDULE = "5 7-19 * * 1-5"


@router.get("/admin/claude")
def claude_status(session: SessionDep, _: Admin) -> ClaudeStatusOut:
    """How the app reaches Claude, and (routine mode) whether the routine is connected and keeping up."""
    pending = select(LlmJob).where(LlmJob.status == "pending")
    routine = llm.routine(session)
    seen = runtime_settings.get(session, "routine_seen_at")
    return ClaudeStatusOut(
        mode="routine" if routine else "api",
        enabled=llm.enabled(session),
        model="Claude Code routine" if routine else settings.llm_model,
        pending=session.scalar(select(func.count()).select_from(pending.subquery())) or 0,
        oldest_pending_at=session.scalar(select(func.min(LlmJob.created_at)).where(LlmJob.status == "pending")),
        last_answer_at=session.scalar(select(func.max(LlmJob.answered_at))),
        api_key_set=bool(settings.anthropic_api_key),
        routine_token_set=llm.routine_token_set(session),
        routine_seen_at=datetime.fromisoformat(seen) if seen else None,
        app_url=settings.app_base_url.rstrip("/"),
        routine_prompt=ROUTINE_PROMPT.read_text(),
        routine_schedule=ROUTINE_SCHEDULE,
    )


@router.put("/admin/claude/mode")
def claude_mode(body: ClaudeModeIn, session: SessionDep, admin: Admin) -> ClaudeStatusOut:
    """Switch between the Claude API and the Claude Code routine. Requests already queued for the routine are asked
    through the API on the next run when switching back."""
    runtime_settings.put(session, "extraction_mode", body.mode)
    session.commit()
    return claude_status(session, admin)


@router.post("/admin/claude/routine-token")
def routine_token(session: SessionDep, admin: Admin) -> RoutineTokenOut:
    """A new token for the routine, replacing the last one made here. Shown once; the app keeps only its hash."""
    token = secrets.token_urlsafe(32)
    runtime_settings.put(session, "routine_token_hash", service.token_hash(token))
    runtime_settings.put(session, "routine_seen_at", None)
    session.commit()
    return RoutineTokenOut(token=token)


@router.delete("/admin/claude/routine-token", status_code=204)
def revoke_routine_token(session: SessionDep, admin: Admin) -> None:
    runtime_settings.put(session, "routine_token_hash", "")
    session.commit()
