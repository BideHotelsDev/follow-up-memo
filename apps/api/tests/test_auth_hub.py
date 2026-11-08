"""Sign in with Bide against a mocked Hub: an RSA key made here signs the tokens, served through a patched JWKS fetch,
and the token endpoint is a patched httpx.post."""

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from bide_followup import auth_hub
from bide_followup.config import settings
from bide_followup.models import User
from tests.conftest import FakeResponse

ISSUER = "http://hub.test"
CLIENT = "meeting-followup"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def sign(claims: dict, key=KEY, kid="k1") -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class Hub:
    def __init__(self) -> None:
        self.token_requests: list[dict] = []
        self.id_claims: dict = {}

    def token(self, url, **kwargs):
        assert url == f"{ISSUER}/oauth/token"
        self.token_requests.append(kwargs)
        return FakeResponse({"id_token": sign(self.id_claims), "access_token": "at", "token_type": "Bearer"})


@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setattr(settings, "bide_hub_issuer", ISSUER + "/")
    monkeypatch.setattr(settings, "bide_hub_client_id", CLIENT)
    monkeypatch.setattr(settings, "bide_hub_client_secret", f"dev-secret-{CLIENT}")
    monkeypatch.setattr(
        auth_hub,
        "discovery",
        lambda: {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/oauth/authorize",
            "token_endpoint": f"{ISSUER}/oauth/token",
            "jwks_uri": f"{ISSUER}/oauth/jwks",
        },
    )
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "use": "sig"}
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    auth_hub._jwks.cache_clear()
    mock = Hub()
    monkeypatch.setattr(auth_hub.httpx, "post", mock.token)
    yield mock
    auth_hub._jwks.cache_clear()


def claims(**extra) -> dict:
    now = int(time.time())
    return {
        "iss": ISSUER,
        "aud": CLIENT,
        "azp": CLIENT,
        "iat": now,
        "exp": now + 300,
        "auth_time": now,
        "amr": ["google"],
        "sid": "sid-1",
        "email_verified": True,
        "name": "Someone",
        **extra,
    }


def round_trip(client, hub: Hub, state: str | None = None, nonce: str | None = None, next_path="/", **extra):
    """Sign-in page → Hub → callback, the Hub answering with an ID token made of claims(**extra)."""
    resp = client.get("/api/auth/bide/login", params={"next": next_path}, follow_redirects=False)
    assert resp.status_code == 307
    q = parse_qs(urlparse(resp.headers["location"]).query)
    hub.id_claims = claims(nonce=nonce or q["nonce"][0], **extra)
    return client.get(
        "/api/auth/bide/callback", params={"code": "c", "state": state or q["state"][0]}, follow_redirects=False
    )


def logout_token(key=KEY, **extra) -> str:
    now = int(time.time())
    body = {
        "iss": ISSUER,
        "aud": CLIENT,
        "iat": now,
        "exp": now + 120,
        "jti": "j",
        "events": {auth_hub.BACKCHANNEL_EVENT: {}},
        **extra,
    }
    return sign({k: v for k, v in body.items() if v is not None}, key)


def test_sign_in_with_bide(client, db, hub):
    resp = client.get("/api/auth/bide/login", params={"next": "/tasks"}, follow_redirects=False)
    location = urlparse(resp.headers["location"])
    q = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{ISSUER}/oauth/authorize"
    assert q["client_id"] == CLIENT and q["response_type"] == "code" and q["scope"] == "openid email profile"
    assert q["redirect_uri"] == "http://localhost:5175/api/auth/bide/callback"
    assert q["code_challenge_method"] == "S256"

    hub.id_claims = claims(sub="hub-sam", email="Sam@bidehotels.com", nonce=q["nonce"])
    resp = client.get("/api/auth/bide/callback", params={"code": "abc", "state": q["state"]}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/tasks"
    assert client.get("/api/auth/me").json()["email"] == "sam@bidehotels.com"
    with db() as s:
        sam = s.query(User).filter_by(email="sam@bidehotels.com").one()
        assert sam.bide_hub_sub == "hub-sam" and sam.last_sign_in_at is not None

    # The code goes back with the client's credentials and the PKCE verifier behind the challenge.
    (req,) = hub.token_requests
    assert req["auth"] == (CLIENT, f"dev-secret-{CLIENT}")
    form = req["data"]
    assert form["grant_type"] == "authorization_code" and form["code"] == "abc"
    assert form["redirect_uri"] == "http://localhost:5175/api/auth/bide/callback"
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == q["code_challenge"]


def test_providers_offer_bide_instead_of_google(client, hub):
    assert client.get("/api/auth/providers").json() == {
        "google": False,
        "dev": True,
        "bide": True,
        "bide_hub_issuer": ISSUER,
    }


def test_wrong_state_is_refused(client, hub):
    resp = round_trip(client, hub, state="forged", sub="hub-sam", email="sam@bidehotels.com")
    assert resp.headers["location"] == "/?login_error=invalid_state"
    assert hub.token_requests == []
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_nonce_is_refused(client, hub):
    resp = round_trip(client, hub, nonce="replayed", sub="hub-sam", email="sam@bidehotels.com")
    assert resp.headers["location"] == "/?login_error=invalid_token"
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "bad",
    [{"aud": "holiday-tracker"}, {"iss": "http://evil.test"}, {"exp": int(time.time()) - 600}],
    ids=["aud", "iss", "expired"],
)
def test_token_for_someone_else_is_refused(client, hub, bad):
    resp = round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com", **bad)
    assert resp.headers["location"] == "/?login_error=invalid_token"
    assert client.get("/api/auth/me").status_code == 401


def test_token_signed_by_another_key_is_refused(client, hub, monkeypatch):
    monkeypatch.setattr(hub, "token", lambda url, **k: FakeResponse({"id_token": sign(hub.id_claims, OTHER_KEY)}))
    monkeypatch.setattr(auth_hub.httpx, "post", hub.token)
    resp = round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com")
    assert resp.headers["location"] == "/?login_error=invalid_token"


def test_uninvited_person_is_refused(client, db, hub):
    resp = round_trip(client, hub, sub="hub-x", email="newcomer@bidehotels.com")
    assert resp.headers["location"] == "/?login_error=not_registered"
    assert client.get("/api/auth/me").status_code == 401
    with db() as s:
        assert s.query(User).filter_by(email="newcomer@bidehotels.com").count() == 0


def test_inactive_or_other_domain_is_refused(client, db, hub):
    with db() as s:
        s.add(User(email="friend@gmail.com", name="Friend"))
        s.query(User).filter_by(email="sam@bidehotels.com").one().is_active = False
        s.commit()
    assert (
        round_trip(client, hub, sub="h1", email="friend@gmail.com").headers["location"].endswith("domain_not_allowed")
    )
    assert round_trip(client, hub, sub="h2", email="sam@bidehotels.com").headers["location"].endswith("not_registered")


def test_hub_refusal_is_shown(client, hub):
    resp = client.get("/api/auth/bide/login", follow_redirects=False)
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    resp = client.get("/api/auth/bide/callback", params={"error": "access_denied", "state": state})
    assert resp.url.path == "/" and resp.url.params["login_error"] == "hub_denied"


def test_links_by_email_then_by_sub(client, db, hub):
    assert round_trip(client, hub, sub="hub-russell", email="russell@bidehotels.com").headers["location"] == "/"
    # Russell's address changes in the Hub; the sub still finds him.
    client.post("/api/auth/logout")
    resp = round_trip(client, hub, sub="hub-russell", email="russell.new@bidehotels.com")
    assert resp.headers["location"] == "/"
    assert client.get("/api/auth/me").json()["email"] == "russell@bidehotels.com"
    # Someone else in the Hub with Russell's address doesn't take over his account.
    client.post("/api/auth/logout")
    resp = round_trip(client, hub, sub="hub-impostor", email="russell@bidehotels.com")
    assert resp.headers["location"] == "/?login_error=not_registered"
    with db() as s:
        assert s.query(User).filter_by(email="russell@bidehotels.com").one().bide_hub_sub == "hub-russell"


def test_backchannel_logout_ends_that_session(client, hub):
    round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com", sid="sid-a")
    assert client.get("/api/auth/me").status_code == 200

    # Another device's session ending leaves this one alone.
    other = logout_token(sub="hub-kyle", sid="sid-b")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": other}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    resp = client.post(
        "/api/auth/bide/backchannel-logout", data={"logout_token": logout_token(sub="hub-kyle", sid="sid-a")}
    )
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_backchannel_logout_without_sid_ends_every_session_of_the_person(client, hub):
    round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com", sid="sid-a")
    token = logout_token(sub="hub-kyle")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_backchannel_logout_leaves_dev_sessions_alone(sign_in, hub):
    client = sign_in("kyle@bidehotels.com")
    token = logout_token(sub="hub-kyle", sid="sid-a")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        lambda: logout_token(sub="hub-kyle", sid="sid-a", nonce="n"),
        lambda: logout_token(sub="hub-kyle", sid="sid-a", events={}),
        lambda: logout_token(sub="hub-kyle", sid="sid-a", aud="holiday-tracker"),
        lambda: logout_token(OTHER_KEY, sub="hub-kyle", sid="sid-a"),
        lambda: "not-a-jwt",
    ],
    ids=["nonce", "no-event", "aud", "signature", "garbage"],
)
def test_backchannel_logout_rejects_bad_tokens(client, hub, token):
    round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com", sid="sid-a")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token()}).status_code == 400
    assert client.get("/api/auth/me").status_code == 200


def test_sign_out_goes_on_to_the_hub(client, hub):
    round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com")
    resp = client.post("/api/auth/logout")
    redirect = urlparse(resp.json()["redirect"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == f"{ISSUER}/oauth/logout"
    assert parse_qs(redirect.query) == {"client_id": [CLIENT], "post_logout_redirect_uri": ["http://localhost:5175/"]}
    assert client.get("/api/auth/me").status_code == 401


def test_flag_off_keeps_the_old_sign_in(client, monkeypatch):
    monkeypatch.setattr(settings, "bide_hub_issuer", ISSUER)
    monkeypatch.setattr(settings, "bide_hub_client_id", CLIENT)
    monkeypatch.setattr(settings, "bide_hub_client_secret", "")  # all three are needed
    assert client.get("/api/auth/providers").json() == {
        "google": True,
        "dev": True,
        "bide": False,
        "bide_hub_issuer": None,
    }
    assert client.get("/api/auth/bide/login", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/bide/callback", params={"code": "c", "state": "s"}).status_code == 404
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": "x"}).status_code == 404
    assert client.get("/api/auth/google/login", follow_redirects=False).status_code == 307
    client.post("/api/auth/dev-login", json={"email": "kyle@bidehotels.com"})
    assert client.post("/api/auth/logout").json() == {"redirect": None}
    assert client.get("/api/auth/me").status_code == 401


def test_google_connect_still_works_with_bide_on(sign_in, db, hub, monkeypatch):
    """Connecting David's Google account (Gmail and Drive access, not a sign-in) goes all the way through."""
    from bide_followup.models import Integration
    from tests.test_connections import connect_google

    client = sign_in("kyle@bidehotels.com")
    resp = connect_google(client, monkeypatch)
    assert resp.headers["location"] == "/admin/connections?connected=google"
    with db() as s:
        assert s.query(Integration).filter_by(provider="google").one().status == "connected"


def test_earlier_sign_out_without_sid_doesnt_end_a_later_session(client, hub, monkeypatch):
    from datetime import timedelta

    from bide_followup import clock
    from tests.conftest import NOW

    token = logout_token(sub="hub-kyle")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token}).status_code == 200
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=5))
    round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com", sid="sid-new")
    assert client.get("/api/auth/me").status_code == 200


def test_google_sign_in_is_closed_with_bide_on(client, hub, monkeypatch):
    resp = client.get("/api/auth/google/login", params={"next": "/tasks"}, follow_redirects=False)
    assert resp.status_code == 307 and resp.headers["location"] == "/api/auth/bide/login?next=%2Ftasks"
    resp = client.get("/api/auth/google/login", params={"next": "//evil.test"}, follow_redirects=False)
    assert resp.headers["location"] == "/api/auth/bide/login?next=%2F"
    # A Google answer that arrives anyway doesn't sign anyone in.
    monkeypatch.setattr(auth_hub.httpx, "post", lambda *a, **k: pytest.fail("Google's token endpoint was called"))
    resp = client.get("/api/auth/google/callback", params={"code": "c", "state": "s"}, follow_redirects=False)
    assert resp.status_code == 404
    assert client.get("/api/auth/me").status_code == 401


def test_dev_login_unchanged_with_bide_on(client, hub, monkeypatch):
    assert client.post("/api/auth/dev-login", json={"email": "kyle@bidehotels.com"}).status_code == 204
    assert client.get("/api/auth/me").json()["email"] == "kyle@bidehotels.com"
    monkeypatch.setattr(settings, "app_base_url", "https://followup.bidehotels.com")
    assert client.post("/api/auth/dev-login", json={"email": "kyle@bidehotels.com"}).status_code == 404


def test_sessions_from_before_the_hub_end_when_it_is_switched_on(client, monkeypatch):
    """A Google session started before the Hub was switched on has no Hub sid, so it's refused while the Hub is on."""
    from tests.test_auth import google_round_trip

    google_round_trip(client, monkeypatch, {"sub": "g-1", "email": "sam@bidehotels.com", "email_verified": True})
    assert client.get("/api/auth/me").status_code == 200
    monkeypatch.setattr(settings, "bide_hub_issuer", ISSUER)
    monkeypatch.setattr(settings, "bide_hub_client_id", CLIENT)
    monkeypatch.setattr(settings, "bide_hub_client_secret", f"dev-secret-{CLIENT}")
    assert client.get("/api/auth/me").status_code == 401


def test_a_dev_login_session_only_counts_while_dev_login_is_allowed(sign_in, hub, monkeypatch):
    client = sign_in("kyle@bidehotels.com")
    assert client.get("/api/auth/me").status_code == 200
    monkeypatch.setattr(settings, "auth_dev_login", False)
    assert client.get("/api/auth/me").status_code == 401


def test_an_id_token_without_a_sid_is_refused(client, hub):
    resp = round_trip(client, hub, sub="hub-kyle", email="kyle@bidehotels.com", sid=None)
    assert resp.headers["location"] == "/?login_error=invalid_token"
    assert client.get("/api/auth/me").status_code == 401


def test_changing_a_persons_email_unlinks_their_sign_in_identities(sign_in, db, hub):
    with db() as s:
        russell = s.query(User).filter_by(email="russell@bidehotels.com").one()
        russell.bide_hub_sub, russell.google_sub = "hub-russell", "g-russell"
        s.commit()
        russell_id = russell.id
    client = sign_in("kyle@bidehotels.com")
    person = next(p for p in client.get("/api/admin/people").json() if p["id"] == str(russell_id))

    # Other changes (or the same address in other case) keep the links.
    assert client.put(f"/api/admin/people/{russell_id}", json={**person, "name": "Russ"}).status_code == 200
    resp = client.put(f"/api/admin/people/{russell_id}", json={**person, "email": "RUSSELL@bidehotels.com"})
    assert resp.status_code == 200
    with db() as s:
        assert (s.get(User, russell_id).bide_hub_sub, s.get(User, russell_id).google_sub) == (
            "hub-russell",
            "g-russell",
        )

    resp = client.put(f"/api/admin/people/{russell_id}", json={**person, "email": "russell.new@bidehotels.com"})
    assert resp.status_code == 200
    with db() as s:
        assert (s.get(User, russell_id).bide_hub_sub, s.get(User, russell_id).google_sub) == (None, None)


def disable_token(sub: str, **extra) -> str:
    """What the Hub sends when an admin switches someone off: the logout event plus account-disabled, no sid."""
    events = {auth_hub.BACKCHANNEL_EVENT: {}, auth_hub.ACCOUNT_DISABLED_EVENT: {}}
    return logout_token(**{"sub": sub, "events": events, **extra})


def test_account_disabled_on_the_hub_switches_the_person_off(client, db, hub, monkeypatch):
    from datetime import timedelta

    from bide_followup import clock
    from bide_followup.models import AuditLog
    from tests.conftest import NOW

    round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com", sid="sid-a")
    assert client.get("/api/auth/me").status_code == 200
    resp = client.post("/api/auth/bide/backchannel-logout", data={"logout_token": disable_token("hub-sam")})
    assert resp.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    with db() as s:
        sam = s.query(User).filter_by(email="sam@bidehotels.com").one()
        assert sam.is_active is False and sam.bide_hub_sub == "hub-sam"
        (entry,) = s.query(AuditLog).filter_by(entity="user").all()
        assert (entry.entity_id, entry.action, entry.user_id) == (sam.id, "update", None)
        assert entry.before == {"is_active": True}
        assert entry.after == {"is_active": False, "reason": "bide_hub_account_disabled"}

    # Signing in again doesn't bring them back: that's an Admin's call here.
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(minutes=5))
    resp = round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com", sid="sid-b")
    assert resp.headers["location"] == "/?login_error=not_registered"
    with db() as s:
        s.query(User).filter_by(email="sam@bidehotels.com").one().is_active = True
        s.commit()
    round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com", sid="sid-c")
    assert client.get("/api/auth/me").status_code == 200


def test_account_disabled_matches_by_hub_identity_only(client, db, hub):
    """No one linked to that sub: nothing changes and the Hub still hears it went through. Never by email."""
    with db() as s:
        s.query(User).filter_by(email="sam@bidehotels.com").one().bide_hub_sub = "hub-sam"
        s.commit()
    token = disable_token("hub-nobody", email="sam@bidehotels.com")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token}).status_code == 200
    with db() as s:
        assert s.query(User).filter_by(is_active=False).count() == 0


@pytest.mark.parametrize(
    "token",
    [
        lambda: disable_token("hub-sam", aud="holiday-tracker"),
        lambda: disable_token("hub-sam", nonce="n"),
        lambda: disable_token("hub-sam", key=OTHER_KEY),
        lambda: logout_token(sub="hub-sam", events={auth_hub.ACCOUNT_DISABLED_EVENT: {}}),
    ],
    ids=["aud", "nonce", "signature", "no-logout-event"],
)
def test_an_unverified_account_disabled_token_changes_nothing(client, db, hub, token):
    round_trip(client, hub, sub="hub-sam", email="sam@bidehotels.com", sid="sid-a")
    assert client.post("/api/auth/bide/backchannel-logout", data={"logout_token": token()}).status_code == 400
    assert client.get("/api/auth/me").status_code == 200
    with db() as s:
        assert s.query(User).filter_by(email="sam@bidehotels.com").one().is_active is True
