import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from bide_followup import runtime_settings
from bide_followup.models import User
from tests.conftest import FakeResponse, id_token


def google_round_trip(client, monkeypatch, claims: dict, start="/api/auth/google/login"):
    resp = client.get(start, follow_redirects=False)
    assert resp.status_code == 307
    q = parse_qs(urlparse(resp.headers["location"]).query)
    claims = {"iss": "https://accounts.google.com", "aud": "google-client", "nonce": q["nonce"][0], **claims}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"id_token": id_token(claims)}))
    return client.get("/api/auth/google/callback", params={"code": "c", "state": q["state"][0]}, follow_redirects=False)


def test_google_sign_in_links_invited_user(client, db, monkeypatch):
    resp = google_round_trip(client, monkeypatch, {"sub": "g-1", "email": "Sam@bidehotels.com", "email_verified": True})
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    assert client.get("/api/auth/me").json()["email"] == "sam@bidehotels.com"
    with db() as s:
        assert s.query(User).filter_by(email="sam@bidehotels.com").one().google_sub == "g-1"


def test_google_sign_in_rejects_uninvited(client, monkeypatch):
    resp = google_round_trip(client, monkeypatch, {"sub": "g-2", "email": "x@bidehotels.com", "email_verified": True})
    assert resp.headers["location"] == "/?login_error=not_registered"
    assert client.get("/api/auth/me").status_code == 401


def test_google_sign_in_rejects_other_domain(client, db, monkeypatch):
    with db() as s:
        s.add(User(email="friend@gmail.com", name="Friend"))
        s.commit()
    resp = google_round_trip(client, monkeypatch, {"sub": "g-3", "email": "friend@gmail.com", "email_verified": True})
    assert resp.headers["location"] == "/?login_error=domain_not_allowed"
    # Admin adds the domain in the app.
    with db() as s:
        runtime_settings.put(s, "internal_domains", ["bidehotels.com", "gmail.com"])
        s.commit()
    resp = google_round_trip(client, monkeypatch, {"sub": "g-3", "email": "friend@gmail.com", "email_verified": True})
    assert resp.headers["location"] == "/"


def test_google_sign_in_rejects_wrong_nonce(client, monkeypatch):
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    claims = {"iss": "https://accounts.google.com", "aud": "google-client", "nonce": "other", "sub": "g"}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"id_token": id_token(claims)}))
    resp = client.get("/api/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert resp.headers["location"] == "/?login_error=invalid_token"


def test_unverified_email_is_not_linked(client, monkeypatch):
    resp = google_round_trip(
        client, monkeypatch, {"sub": "g-4", "email": "sam@bidehotels.com", "email_verified": False}
    )
    assert resp.headers["location"] == "/?login_error=not_registered"


def test_dev_login_only_on_localhost(client, monkeypatch):
    from bide_followup.config import settings

    monkeypatch.setattr(settings, "app_base_url", "https://followup.bidehotels.com")
    assert client.post("/api/auth/dev-login", json={"email": "kyle@bidehotels.com"}).status_code == 404


def test_logout(sign_in):
    client = sign_in("david@liddellpropertyinvestments.com")
    assert client.get("/api/auth/me").json()["role"] == "owner"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def _start_app(**env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import bide_followup.main"],
        cwd=Path(__file__).parents[1],
        env=os.environ | env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_deployment_refuses_to_start_without_its_secrets():
    """Outside localhost, a random session key or no token key won't do: staging and production both need them."""
    deployed = {"APP_BASE_URL": "https://followup.bidehotels.com"}
    refused = _start_app(**deployed, SESSION_SECRET="", TOKEN_ENCRYPTION_KEY="")
    assert refused.returncode != 0 and "SESSION_SECRET and TOKEN_ENCRYPTION_KEY must be set" in refused.stderr
    refused = _start_app(**deployed, SESSION_SECRET="s3cret", TOKEN_ENCRYPTION_KEY="")
    assert refused.returncode != 0 and "TOKEN_ENCRYPTION_KEY must be set" in refused.stderr
    assert _start_app(**deployed, SESSION_SECRET="s3cret", TOKEN_ENCRYPTION_KEY="k").returncode == 0
    local = _start_app(APP_BASE_URL="http://localhost:5175", SESSION_SECRET="", TOKEN_ENCRYPTION_KEY="")
    assert local.returncode == 0
