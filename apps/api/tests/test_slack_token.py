import io
import sys

from slack_sdk.web import SlackResponse

from bide_followup import slack_token
from bide_followup.integrations import slack


def fake_auth_test(scopes: str):
    def auth_test(self):
        return SlackResponse(
            client=self,
            http_verb="POST",
            api_url="auth.test",
            req_args={},
            data={"ok": True, "team": "Bide", "team_id": "T1", "user": "bide_followup"},
            headers={"x-oauth-scopes": scopes},
            status_code=200,
        )

    return auth_test


def run(monkeypatch, db, token: str, scopes: str) -> int:
    monkeypatch.setattr(slack_token, "SessionLocal", db)
    monkeypatch.setattr("slack_sdk.WebClient.auth_test", fake_auth_test(scopes))
    monkeypatch.setattr(sys, "stdin", io.StringIO(token + "\n"))
    return slack_token.main()


def test_stores_encrypted_token(monkeypatch, db):
    assert run(monkeypatch, db, "xoxb-1", ",".join(slack.BOT_SCOPES)) == 0
    with db() as s:
        assert slack.client(s).token == "xoxb-1"
        assert "xoxb-1" not in slack.integration(s).encrypted_tokens


def test_refuses_missing_scopes_and_non_bot_tokens(monkeypatch, db):
    assert run(monkeypatch, db, "xoxb-1", "chat:write") == 1
    assert run(monkeypatch, db, "xapp-1", ",".join(slack.BOT_SCOPES)) == 1
    with db() as s:
        assert slack.integration(s) is None
