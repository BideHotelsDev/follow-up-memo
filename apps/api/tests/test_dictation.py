import pytest
from fastapi.testclient import TestClient

from bide_followup.config import settings
from bide_followup.integrations import wispr
from mocks import server


@pytest.fixture
def wispr_mock(monkeypatch):
    mock = TestClient(server.app, base_url="http://mock")
    server.reset()
    monkeypatch.setattr(settings, "wispr_api_key", "mock-key")
    monkeypatch.setattr(settings, "wispr_api_url", "http://mock/wispr")
    monkeypatch.setattr(
        wispr.httpx, "post", lambda url, **k: mock.post(url, **{a: b for a, b in k.items() if a != "timeout"})
    )
    return mock


def test_without_a_key_there_is_no_microphone(sign_in):
    client = sign_in("sam@bidehotels.com")
    assert client.get("/api/app").json()["dictation"] is False
    assert client.post("/api/dictation/token").status_code == 503


def test_anyone_signed_in_gets_a_short_lived_token_and_the_names(sign_in, wispr_mock):
    client = sign_in("sam@bidehotels.com")
    assert client.get("/api/app").json()["dictation"] is True
    out = client.post("/api/dictation/token").json()
    assert out["access_token"].startswith("mock-wispr-")
    assert out["expires_in"] == wispr.TOKEN_SECONDS
    assert out["ws_url"] == "ws://mock/wispr/api/v1/dash/client_ws"
    assert "Bide" in out["dictionary"] and any("Russell" in w for w in out["dictionary"])
    assert "mock-key" not in str(out)  # the org key stays on the server


def test_a_rejected_key_is_a_clear_error(sign_in, wispr_mock, monkeypatch):
    monkeypatch.setattr(settings, "wispr_api_key", "wrong")
    resp = sign_in("david@liddellpropertyinvestments.com").post("/api/dictation/token")
    assert resp.status_code == 502 and "invalid_key" in resp.text


def test_the_mock_transcribes_what_the_browser_streams(sign_in, wispr_mock):
    token = sign_in("david@liddellpropertyinvestments.com").post("/api/dictation/token").json()["access_token"]
    with wispr_mock.websocket_connect("/wispr/api/v1/dash/client_ws") as ws:
        ws.send_json({"type": "auth", "access_token": token, "context": {"app": {"type": "email"}}})
        assert ws.receive_json() == {"status": "auth"}
        packet = {"packets": ["AAAA", "AAAA"], "volumes": [0, 0], "packet_duration": 1, "audio_encoding": "wav"}
        ws.send_json({"type": "append", "position": 0, "audio_packets": packet})
        ws.send_json({"type": "append", "position": 2, "audio_packets": packet})
        ws.send_json({"type": "commit", "total_packets": 4})
        assert ws.receive_json()["message"]["event"] == "commit_received"
        final = ws.receive_json()
    assert final["final"] is True and final["body"]["text"] == server.DICTATED
    assert server.state["dictations"][-1]["packets"] == 4
