"""Accounts managed by Bide Hub: the Hub pushes people and their role; Follow-up follows (hub_accounts.py).

The Hub is bide-hub-client's FakeHub, which signs provisioning tokens with the key whose public half it serves."""

import json

import pytest

from bide_followup import auth_hub, clock, hub_accounts
from bide_followup._vendor.bide_hub_client.testing import FakeHub
from bide_followup.config import settings
from bide_followup.models import User

BASE = "http://localhost:5175"
PATH = hub_accounts.PATH


@pytest.fixture
def hub(monkeypatch):
    fake = FakeHub(issuer="http://hub.test", client_id="meeting-followup", client_secret="dev-secret-meeting-followup")
    monkeypatch.setattr(settings, "bide_hub_issuer", fake.issuer)
    monkeypatch.setattr(settings, "bide_hub_client_id", fake.client_id)
    monkeypatch.setattr(settings, "bide_hub_client_secret", fake.client_secret)
    monkeypatch.setattr(settings, "bide_hub_manages_accounts", True)
    client = fake.client(now=lambda: clock.utcnow().timestamp())
    monkeypatch.setattr(auth_hub, "hub", lambda: client)
    return fake


def call(client, hub: FakeHub, method: str, path: str, payload: dict | None = None, **token_claims):
    body = b"" if payload is None else json.dumps(payload).encode()
    token = hub.provisioning_token(method, f"{BASE}{PATH}{path}", body, **token_claims)
    headers = {"Authorization": f"Bearer {token}"} | ({"Content-Type": "application/json"} if body else {})
    return client.request(method, f"{PATH}{path}", content=body or None, headers=headers)


def account(email: str, role: str | None = "member", active: bool = True, name: str = "Someone") -> dict:
    return {
        "email": email,
        "name": name,
        "active": active,
        "assignments": [] if role is None else [{"role": role, "scope": None}],
    }


def user(db, email: str) -> User | None:
    with db() as s:
        return s.query(User).filter_by(email=email).one_or_none()


# --- reading ----------------------------------------------------------------------------------------------------------


def test_off_unless_the_operator_turns_it_on(client, hub, monkeypatch):
    monkeypatch.setattr(settings, "bide_hub_manages_accounts", False)
    assert call(client, hub, "GET", "/catalog").status_code == 404


def test_catalog_offers_one_role_from_three(client, hub):
    body = call(client, hub, "GET", "/catalog").json()
    assert [r["key"] for r in body["roles"]] == ["owner", "admin", "member"]
    assert not any(r["scoped"] for r in body["roles"]) and body["scopes"] == []
    assert body["max_assignments"] == 1 and body["features"] == ["check"]


def test_the_accounts_here_for_the_hubs_import(client, hub):
    rows = {r["email"]: r for r in call(client, hub, "GET", "/users").json()}
    assert rows["david@liddellpropertyinvestments.com"]["assignments"] == [{"role": "owner", "scope": None}]
    assert rows["sam@bidehotels.com"]["active"] is True and rows["sam@bidehotels.com"]["sub"] is None


@pytest.mark.parametrize(
    "claims",
    [{"aud": "linen-tracker"}, {"htu": f"{BASE}{PATH}/users"}, {"purpose": "something-else"}, {"htm": "POST"}],
    ids=["aud", "address", "purpose", "method"],
)
def test_a_token_for_anything_else_is_refused(client, hub, claims):
    assert call(client, hub, "GET", "/catalog", **claims).status_code == 401


def test_no_token_is_refused(client, hub):
    assert client.get(f"{PATH}/catalog").status_code == 401


# --- changing ---------------------------------------------------------------------------------------------------------


def test_a_new_person_gets_an_account_and_repeating_it_changes_nothing(client, db, hub):
    for _ in range(2):  # the Hub may send the same PUT more than once
        r = call(client, hub, "PUT", "/users/hub-new", account("New.Person@bidehotels.com", name="New Person"))
        assert r.status_code == 200, r.text
    with db() as s:
        [u] = s.query(User).filter_by(bide_hub_sub="hub-new").all()
        assert (u.email, u.name, u.role, u.is_active) == ("new.person@bidehotels.com", "New Person", "member", True)


def test_an_existing_account_is_linked_by_email_and_follows_the_hub(client, db, hub):
    r = call(client, hub, "PUT", "/users/hub-sam", account("sam@bidehotels.com", role="admin", name="Sam S"))
    assert r.status_code == 200, r.text
    sam = user(db, "sam@bidehotels.com")
    assert (sam.bide_hub_sub, sam.role, sam.name) == ("hub-sam", "admin", "Sam S")
    assert sam.slack_user_id == "U0SAM" and sam.ownership_areas == ["revenue"], "what is Follow-up's own stays"

    r = call(client, hub, "PUT", "/users/hub-sam", account("sam.s@bidehotels.com", role="admin", name="Sam S"))
    assert r.status_code == 200 and user(db, "sam.s@bidehotels.com").bide_hub_sub == "hub-sam"


@pytest.mark.parametrize(
    ("roles", "says"),
    [([], "pick a role"), (["member", "admin"], "one role"), (["boss"], "no role 'boss'")],
    ids=["none", "two", "unknown"],
)
def test_what_follow_up_cant_apply_is_refused(client, db, hub, roles, says):
    payload = account("sam@bidehotels.com") | {"assignments": [{"role": r, "scope": None} for r in roles]}
    r = call(client, hub, "PUT", "/users/hub-sam", payload)
    assert r.status_code == 422 and says in r.json()["detail"]
    assert user(db, "sam@bidehotels.com").bide_hub_sub is None


def test_an_email_that_is_another_hub_persons_is_refused(client, db, hub):
    call(client, hub, "PUT", "/users/hub-sam", account("sam@bidehotels.com"))
    r = call(client, hub, "PUT", "/users/hub-impostor", account("sam@bidehotels.com"))
    assert r.status_code == 409 and "different Hub person" in r.json()["detail"]


def test_switching_off_never_creates_and_is_never_refused(client, db, hub):
    assert call(client, hub, "PUT", "/users/hub-ghost", account("ghost@bidehotels.com", active=False)).json() == {
        "id": None,
        "active": False,
    }
    assert user(db, "ghost@bidehotels.com") is None
    call(client, hub, "PUT", "/users/hub-sam", account("sam@bidehotels.com"))
    r = call(client, hub, "PUT", "/users/hub-sam", account("sam@bidehotels.com", role=None, active=False))
    assert r.status_code == 200 and user(db, "sam@bidehotels.com").is_active is False


def test_someone_stays_in_charge(client, db, hub):
    """Demoting the last owner or admin is refused when the Hub asks first; a PUT of a change the Hub already saved
    is applied (the fix is made in the Hub), and switching them off is never refused."""
    call(client, hub, "PUT", "/users/hub-kyle", account("kyle@bidehotels.com", role="member"))  # David is still owner
    demote = account("david@liddellpropertyinvestments.com", role="member", name="David")
    r = call(client, hub, "POST", "/users/hub-david/check", demote)
    assert r.status_code == 409 and "at least one active owner or admin" in r.json()["detail"]
    assert user(db, "david@liddellpropertyinvestments.com").role == "owner", "a check changes nothing"

    off = account("david@liddellpropertyinvestments.com", role=None, active=False, name="David")
    r = call(client, hub, "POST", "/users/hub-david/check", off)
    assert r.status_code == 200 and "last active owner or admin" in r.json()["warnings"][0]
    assert call(client, hub, "PUT", "/users/hub-david", demote).status_code == 200
    assert user(db, "david@liddellpropertyinvestments.com").role == "member"


def test_a_check_answers_like_the_put_and_changes_nothing(client, db, hub):
    r = call(client, hub, "POST", "/users/hub-new/check", account("new@bidehotels.com"))
    assert r.json() == {"ok": True, "warnings": []}
    assert user(db, "new@bidehotels.com") is None
    assert (
        call(client, hub, "POST", "/users/hub-new/check", account("new@bidehotels.com", role=None)).status_code == 422
    )


# --- Admin → People while the Hub manages accounts --------------------------------------------------------------------


def test_people_admin_keeps_only_what_is_follow_ups_own(sign_in, db, hub):
    client = sign_in("kyle@bidehotels.com")
    assert client.get("/api/auth/providers").json()["accounts_managed_by_hub"] is True
    new = {"email": "x@bidehotels.com", "name": "X"}
    assert client.post("/api/admin/people", json=new).json()["code"] == "managed_by_hub"

    sam = next(p for p in client.get("/api/admin/people").json() if p["email"] == "sam@bidehotels.com")
    keep = {k: sam[k] for k in ("email", "name", "role", "slack_user_id", "ownership_areas", "is_active")}
    assert (
        client.put(f"/api/admin/people/{sam['id']}", json=keep | {"role": "admin"}).json()["code"] == "managed_by_hub"
    )
    r = client.put(f"/api/admin/people/{sam['id']}", json=keep | {"ownership_areas": ["revenue", "pricing"]})
    assert r.status_code == 200 and r.json()["ownership_areas"] == ["revenue", "pricing"]
