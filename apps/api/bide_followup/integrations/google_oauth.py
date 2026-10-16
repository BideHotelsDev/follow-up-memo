"""David's Google account: the stored refresh token and fresh access tokens for Drive, Calendar and Gmail.

Scopes are least-privilege (PRD §5). gmail.compose would also allow sending; gmail.py never calls a send endpoint
and a test holds it to that, so "nothing is sent without approval" does not rest on the scope.
"""

from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import clock, crypto
from bide_followup.config import settings
from bide_followup.models import Integration

SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
)


class GoogleAuthError(Exception):
    """The connection can't be used: never connected, revoked, or Google refused the refresh."""


def integration(session: Session) -> Integration | None:
    return session.scalar(select(Integration).where(Integration.provider == "google"))


def save(session: Session, email: str, token_body: dict) -> Integration:
    """Store the token response from the connect flow. Google only returns a refresh token on consent."""
    row = integration(session)
    tokens = crypto.decrypt(row.encrypted_tokens) if row else {}
    if token_body.get("refresh_token"):
        tokens["refresh_token"] = token_body["refresh_token"]
    if not tokens.get("refresh_token"):
        raise GoogleAuthError("Google returned no refresh token")
    tokens["access_token"] = token_body["access_token"]
    expires_at = clock.utcnow() + timedelta(seconds=int(token_body.get("expires_in", 3600)))
    tokens["access_expires_at"] = expires_at.isoformat()
    if row is None:
        row = Integration(provider="google", encrypted_tokens="")
        session.add(row)
    row.account_email = email
    row.encrypted_tokens = crypto.encrypt(tokens)
    row.scopes = token_body.get("scope", " ".join(SCOPES)).split()
    row.expires_at = expires_at
    row.status = "connected"
    row.last_error = None
    session.commit()
    return row


def access_token(session: Session) -> str:
    """A valid access token, refreshed when it is within a minute of expiry."""
    row = integration(session)
    if row is None or row.status == "revoked":
        raise GoogleAuthError("Google account not connected")
    tokens = crypto.decrypt(row.encrypted_tokens)
    if row.expires_at and row.expires_at - clock.utcnow() > timedelta(minutes=1):
        return tokens["access_token"]
    resp = httpx.post(
        settings.google_token_url,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.is_error:
        # invalid_grant = revoked or expired consent: runs pause until Admin reconnects.
        row.status = "revoked" if "invalid_grant" in resp.text else "error"
        row.last_error = f"token refresh failed ({resp.status_code})"
        session.commit()
        raise GoogleAuthError(row.last_error)
    body = resp.json()
    tokens["access_token"] = body["access_token"]
    row.expires_at = clock.utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)))
    row.encrypted_tokens = crypto.encrypt(tokens)
    row.status, row.last_error = "connected", None
    session.commit()
    return tokens["access_token"]
