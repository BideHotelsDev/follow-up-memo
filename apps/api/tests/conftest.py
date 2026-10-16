import base64
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bide_followup import clock
from bide_followup.config import settings
from bide_followup.db import get_session
from bide_followup.main import app
from bide_followup.models import Base, User

NOW = datetime(2026, 10, 13, 15, 0, tzinfo=ZoneInfo("Europe/London"))  # a Tuesday afternoon


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:5175")
    monkeypatch.setattr(settings, "auth_dev_login", True)
    monkeypatch.setattr(settings, "bide_domains", "bidehotels.com,liddellpropertyinvestments.com")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_client_id", "google-client")
    monkeypatch.setattr(settings, "google_client_secret", "google-secret")
    monkeypatch.setattr(settings, "slack_client_id", "slack-client")
    monkeypatch.setattr(settings, "slack_client_secret", "slack-secret")
    monkeypatch.setattr(settings, "anthropic_api_key", "")


@pytest.fixture
def db():
    """Session factory over an in-memory SQLite copy of the schema, seeded with David (owner), Kyle (admin),
    Russell and Sam (members)."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def fk(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        s.add_all(
            [
                User(email="david@liddellpropertyinvestments.com", name="David", role="owner"),
                User(email="kyle@bidehotels.com", name="Kyle", role="admin"),
                User(
                    email="russell@bidehotels.com",
                    name="Russell",
                    slack_user_id="U0RUSSELL",
                    ownership_areas=["operations", "housekeeping"],
                ),
                User(email="sam@bidehotels.com", name="Sam", slack_user_id="U0SAM", ownership_areas=["revenue"]),
            ]
        )
        s.commit()
    return factory


@pytest.fixture
def client(db):
    def override():
        with db() as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sign_in(client):
    """sign_in("kyle@bidehotels.com") signs the test client in through the dev login."""

    def go(email: str) -> TestClient:
        client.cookies.clear()
        resp = client.post("/api/auth/dev-login", json={"email": email})
        assert resp.status_code == 204, resp.text
        return client

    return go


def id_token(claims: dict) -> str:
    """An unsigned JWT-shaped ID token (the app reads claims without checking the signature; see auth.py)."""

    def enc(part: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")

    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


class FakeResponse:
    def __init__(self, body: dict, status: int = 200):
        self._body, self.status_code = body, status
        self.content = json.dumps(body).encode()
        self.text = self.content.decode()
        self.is_error = status >= 400

    def json(self) -> dict:
        return self._body


@pytest.fixture
def mocks(monkeypatch):
    """Google and Claude served by mocks/server.py in-process, with David's Google account connected."""
    import anthropic
    import httpx

    from bide_followup.integrations import google_api, google_oauth, llm
    from mocks import server

    mock = TestClient(server.app, base_url="http://mock")
    server.reset(NOW)
    monkeypatch.setattr(settings, "google_api_url", "http://mock/google")
    monkeypatch.setattr(settings, "google_token_url", "http://mock/google/token")
    monkeypatch.setattr(settings, "anthropic_api_key", "mock-key")
    monkeypatch.setattr(settings, "gmail_api_url", "http://mock/gmail")

    def get(url, **kwargs):
        return mock.get(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    def post(url, **kwargs):
        return mock.post(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    def put(url, **kwargs):
        return mock.put(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    def delete(url, **kwargs):
        return mock.delete(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    # One httpx module serves every integration, so these patches cover Google, Gmail and the token refresh.
    monkeypatch.setattr(google_api.httpx, "get", get)
    monkeypatch.setattr(google_oauth.httpx, "post", post)
    monkeypatch.setattr(google_api.httpx, "put", put)
    monkeypatch.setattr(google_api.httpx, "delete", delete)
    monkeypatch.setattr(
        llm,
        "client",
        lambda: anthropic.Anthropic(api_key="mock-key", base_url="http://mock/anthropic", http_client=mock),
    )
    assert httpx  # imported for the patch targets above
    return server


@pytest.fixture
def connected(db):
    """David's Google account connected (an expired access token, so the first call refreshes through the mock)."""
    from bide_followup.integrations import google_oauth

    with db() as s:
        google_oauth.save(
            s,
            "david@liddellpropertyinvestments.com",
            {"access_token": "old", "refresh_token": "1//r", "expires_in": 0},
        )


class MockSlack:
    """The parts of slack_sdk's WebClient the app uses, served by the mock (WebClient itself uses urllib, which
    can't reach an in-process TestClient)."""

    def __init__(self, mock: TestClient):
        self.mock = mock
        self.token = "xoxb-mock"

    def _call(self, method: str, **kwargs):
        from slack_sdk.errors import SlackApiError

        body = self.mock.post(f"/slack/api/{method}", json=kwargs).json()
        if not body.get("ok"):
            raise SlackApiError(body.get("error", "error"), body)
        return body

    def conversations_open(self, **kwargs):
        return self._call("conversations.open", **kwargs)

    def chat_postMessage(self, **kwargs):  # slack_sdk's name
        return self._call("chat.postMessage", **kwargs)

    def users_lookupByEmail(self, **kwargs):
        return self._call("users.lookupByEmail", **kwargs)


@pytest.fixture
def slack_bot(monkeypatch, mocks):
    """The Slack bot installed, posting to the mock (read back from mocks.state["slack"])."""
    from bide_followup.integrations import slack

    bot = MockSlack(TestClient(mocks.app, base_url="http://mock"))
    monkeypatch.setattr(slack, "client", lambda session: bot)
    return mocks.state["slack"]
