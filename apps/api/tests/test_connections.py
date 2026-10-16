from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from bide_followup import clock, crypto
from bide_followup.integrations import google_oauth, slack
from bide_followup.models import Integration
from tests.conftest import FakeResponse, id_token

GRANTED = " ".join(google_oauth.SCOPES)


def connect_google(client, monkeypatch, body_extra: dict | None = None):
    resp = client.get("/api/auth/google/connect", follow_redirects=False)
    assert resp.status_code == 307
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert "https://www.googleapis.com/auth/gmail.compose" in q["scope"][0]
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "google-client",
        "nonce": q["nonce"][0],
        "sub": "g-david",
        "email": "david@liddellpropertyinvestments.com",
    }
    body = {
        "id_token": id_token(claims),
        "access_token": "ya29.access",
        "refresh_token": "1//refresh",
        "expires_in": 3599,
        "scope": GRANTED,
        **(body_extra or {}),
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(body))
    return client.get(
        "/api/auth/google/connect/callback", params={"code": "c", "state": q["state"][0]}, follow_redirects=False
    )


def test_only_admin_can_connect(sign_in):
    client = sign_in("david@liddellpropertyinvestments.com")
    assert client.get("/api/auth/google/connect", follow_redirects=False).status_code == 403


def test_google_connect_stores_encrypted_tokens(sign_in, db, monkeypatch):
    client = sign_in("kyle@bidehotels.com")
    resp = connect_google(client, monkeypatch)
    assert resp.headers["location"] == "/admin/connections?connected=google"
    with db() as s:
        row = s.query(Integration).filter_by(provider="google").one()
        assert "1//refresh" not in row.encrypted_tokens  # encrypted at rest
        assert crypto.decrypt(row.encrypted_tokens)["refresh_token"] == "1//refresh"
        assert row.account_email == "david@liddellpropertyinvestments.com"
    out = client.get("/api/admin/connections").json()
    assert out["google"]["status"] == "connected" and out["slack"] is None
    assert "refresh" not in str(out)


def test_google_connect_refuses_missing_scopes(sign_in, monkeypatch):
    client = sign_in("kyle@bidehotels.com")
    resp = connect_google(client, monkeypatch, {"scope": "openid email"})
    assert resp.headers["location"] == "/admin/connections?error=scopes_missing"


def test_access_token_refreshes_and_marks_revoked(sign_in, db, monkeypatch):
    client = sign_in("kyle@bidehotels.com")
    connect_google(client, monkeypatch)
    with db() as s:
        assert google_oauth.access_token(s) == "ya29.access"  # still fresh
        s.query(Integration).one().expires_at = clock.utcnow() - timedelta(minutes=5)
        s.commit()
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"access_token": "ya29.new"}))
        assert google_oauth.access_token(s) == "ya29.new"
        s.query(Integration).one().expires_at = clock.utcnow()
        s.commit()
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"error": "invalid_grant"}, 400))
        with pytest.raises(google_oauth.GoogleAuthError):
            google_oauth.access_token(s)
        assert s.query(Integration).one().status == "revoked"


def test_slack_install(sign_in, db, monkeypatch):
    client = sign_in("kyle@bidehotels.com")
    resp = client.get("/api/auth/slack/install", follow_redirects=False)
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert "groups:read" in q["scope"][0] and "chat:write" in q["scope"][0]
    body = {
        "ok": True,
        "access_token": "xoxb-1",
        "scope": ",".join(slack.BOT_SCOPES),
        "team": {"id": "T1", "name": "Bide"},
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse(body))
    resp = client.get("/api/auth/slack/callback", params={"code": "c", "state": q["state"][0]}, follow_redirects=False)
    assert resp.headers["location"] == "/admin/connections?connected=slack"
    with db() as s:
        assert slack.client(s).token == "xoxb-1"


def test_slack_install_rejects_bad_state(sign_in):
    client = sign_in("kyle@bidehotels.com")
    client.get("/api/auth/slack/install", follow_redirects=False)
    resp = client.get("/api/auth/slack/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert resp.headers["location"] == "/admin/connections?error=slack_error"


def test_wrong_key_is_unreadable(monkeypatch):
    from cryptography.fernet import Fernet

    from bide_followup.config import settings
    from bide_followup.errors import DomainError

    blob = crypto.encrypt({"a": 1})
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(DomainError):
        crypto.decrypt(blob)
