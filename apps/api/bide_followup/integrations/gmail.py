"""Gmail drafts in David's mailbox (PRD FR-20). Drafts only: nothing in this module sends.

The gmail.compose scope would let the token send mail, so "no email is ever sent" rests here, and
tests/test_gmail.py fails if this module ever names a send endpoint.
"""

import base64
from email.message import EmailMessage

import httpx

from bide_followup.config import settings


class GmailError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Gmail {status}: {message}")
        self.status = status


def _url(path: str = "") -> str:
    return f"{settings.gmail_api_url}/gmail/v1/users/me/drafts{path}"


def _check(resp: httpx.Response) -> httpx.Response:
    if resp.is_error:
        reason = ""
        if resp.headers.get("content-type", "").startswith("application/json"):
            reason = resp.json().get("error", {}).get("status", "")
        raise GmailError(resp.status_code, reason or resp.reason_phrase)
    return resp


def _raw(to: list[str], subject: str, body: str) -> str:
    message = EmailMessage()
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_draft(token: str, to: list[str], subject: str, body: str) -> str:
    """Create a draft and return its ID."""
    payload = {"message": {"raw": _raw(to, subject, body)}}
    return _check(httpx.post(_url(), json=payload, headers=_headers(token), timeout=30)).json()["id"]


def update_draft(token: str, draft_id: str, to: list[str], subject: str, body: str) -> str:
    payload = {"id": draft_id, "message": {"raw": _raw(to, subject, body)}}
    return _check(httpx.put(_url(f"/{draft_id}"), json=payload, headers=_headers(token), timeout=30)).json()["id"]


def delete_draft(token: str, draft_id: str) -> None:
    resp = httpx.delete(_url(f"/{draft_id}"), headers=_headers(token), timeout=30)
    if resp.status_code != 404:  # already gone is fine
        _check(resp)


def draft_exists(token: str, draft_id: str) -> bool:
    """False once David has sent or deleted the draft in Gmail (the compose scope can't tell which)."""
    resp = httpx.get(_url(f"/{draft_id}"), params={"format": "minimal"}, headers=_headers(token), timeout=30)
    if resp.status_code == 404:
        return False
    _check(resp)
    return True


def open_url(draft_id: str) -> str:
    """Where David opens the draft in Gmail."""
    return f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}"
