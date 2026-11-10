"""Fixes from the auth review: sessions end SESSION_DAYS after sign-in and are cleared when refused; an email change or
a switch-off ends sessions; someone stays in charge; linking by email needs the Hub to have verified it; the Hub's
settings come together; one owner everywhere; emails unique ignoring case."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from bide_followup import auth, catalog, clock, impact
from bide_followup.config import settings
from bide_followup.errors import DomainError
from bide_followup.main import app
from bide_followup.models import AuditLog, User
from bide_followup.routers import admin
from tests.conftest import NOW
from tests.test_auth_hub import hub, round_trip  # noqa: F401  (hub is a fixture)


def _people(client) -> dict[str, dict]:
    return {p["name"]: p for p in client.get("/api/admin/people").json()}


def _browser(email: str) -> TestClient:
    other = TestClient(app)
    assert other.post("/api/auth/dev-login", json={"email": email}).status_code == 204
    return other


def test_a_session_ends_session_days_after_sign_in_however_often_its_used(sign_in, monkeypatch):
    client = sign_in("sam@bidehotels.com")
    for days in (1, 7, settings.session_days - 1):
        monkeypatch.setattr(clock, "now", lambda d=days: NOW + timedelta(days=d))
        assert client.get("/api/auth/me").status_code == 200
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=settings.session_days, minutes=1))
    assert client.get("/api/auth/me").status_code == 401
    # Cleared, not just refused: going back in time doesn't make the cookie work again.
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=1))
    assert client.get("/api/auth/me").status_code == 401


def test_a_session_from_before_sessions_recorded_their_start_is_refused():
    user = User(email="sam@bidehotels.com", name="Sam")
    assert auth._expired(Request({"type": "http", "session": {"user_id": "x"}}), user) is True
    fresh = {"user_id": "x", "signed_in_at": clock.utcnow().isoformat()}
    assert auth._expired(Request({"type": "http", "session": fresh}), user) is False


def test_changing_an_email_signs_out_the_old_address(sign_in, client, db, monkeypatch):
    sams_browser = _browser("sam@bidehotels.com")
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=1))
    with db() as session:
        session.scalar(select(User).where(User.name == "Sam")).google_sub = "g-sam"
        session.commit()
    sign_in("kyle@bidehotels.com")
    sam = _people(client)["Sam"]
    assert client.put(f"/api/admin/people/{sam['id']}", json={**sam, "email": "samuel@bidehotels.com"}).status_code == 200

    assert sams_browser.get("/api/auth/me").status_code == 401
    with db() as session:
        assert session.scalar(select(User).where(User.name == "Sam")).google_sub is None
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=2))
    assert _browser("samuel@bidehotels.com").get("/api/auth/me").status_code == 200


def test_switching_someone_back_on_doesnt_revive_their_old_session(sign_in, client, monkeypatch):
    sams_browser = _browser("sam@bidehotels.com")
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=1))
    sign_in("kyle@bidehotels.com")
    sam = _people(client)["Sam"]
    client.put(f"/api/admin/people/{sam['id']}", json={**sam, "is_active": False})
    client.put(f"/api/admin/people/{sam['id']}", json={**sam, "is_active": True})
    assert sams_browser.get("/api/auth/me").status_code == 401


def test_the_last_active_owner_or_admin_cant_be_switched_off_or_demoted(db):
    with db() as session:
        david = session.scalar(select(User).where(User.name == "David"))
        kyle = session.scalar(select(User).where(User.name == "Kyle"))
        admin._keep_someone_in_charge(session, david)  # Kyle is still there
        kyle.is_active = False  # e.g. switched off a moment ago by someone else
        session.flush()
        with pytest.raises(DomainError) as refused:
            admin._keep_someone_in_charge(session, david)
        assert refused.value.code == "last_admin"


def test_the_last_in_charge_guard_runs_on_the_people_screen(sign_in, client, db, monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "_keep_someone_in_charge", lambda session, user: calls.append(user.name))
    sign_in("kyle@bidehotels.com")
    people = _people(client)
    client.put(f"/api/admin/people/{people['David']['id']}", json={**people["David"], "role": "member"})
    client.put(f"/api/admin/people/{people['Sam']['id']}", json={**people["Sam"], "is_active": False})
    assert calls == ["David"]  # only for someone in charge


def test_linking_by_email_needs_the_hub_to_have_verified_it(client, db, hub):  # noqa: F811
    resp = round_trip(client, hub, sub="hub-new", email="sam@bidehotels.com", email_verified=False)
    assert "login_error=not_registered" in resp.headers["location"]
    with db() as session:
        assert session.scalar(select(User).where(User.name == "Sam")).bide_hub_sub is None


@pytest.mark.parametrize(
    ("issuer", "client_id", "secret", "missing"),
    [
        ("", "", "", []),
        ("https://hub", "memo", "s", []),
        ("https://hub", "", "", ["BIDE_HUB_CLIENT_ID", "BIDE_HUB_CLIENT_SECRET"]),
        ("", "memo", "s", ["BIDE_HUB_ISSUER"]),
    ],
)
def test_the_hub_settings_come_all_together_or_not_at_all(monkeypatch, issuer, client_id, secret, missing):
    monkeypatch.setattr(settings, "bide_hub_issuer", issuer)
    monkeypatch.setattr(settings, "bide_hub_client_id", client_id)
    monkeypatch.setattr(settings, "bide_hub_client_secret", secret)
    assert settings.partial_hub_settings() == missing


def test_impact_follows_the_active_owner(sign_in, db, monkeypatch):
    with db() as session:
        session.scalar(select(User).where(User.name == "David")).is_active = False
        olivia = User(email="olivia@bidehotels.com", name="Olivia", role="owner")
        session.add(olivia)
        session.flush()
        session.add(AuditLog(user_id=olivia.id, entity="user", entity_id=olivia.id, action="update"))
        session.commit()
        assert catalog.owner(session).name == "Olivia"
        assert impact.compute(session).david_active_days == 1


def test_emails_are_unique_ignoring_case(db):
    with db() as session:
        session.add(User(email="Sam@BideHotels.com", name="Sam again"))
        with pytest.raises(IntegrityError):
            session.commit()
