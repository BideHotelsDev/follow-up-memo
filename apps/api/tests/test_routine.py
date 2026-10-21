"""Routine mode: Claude requests wait in a queue that the Claude Code routine answers through the service API."""

import json

import pytest
from sqlalchemy import select

from bide_followup.config import settings
from bide_followup.models import LlmJob, Meeting, Output, Setting
from bide_followup.pipeline import run

TOKEN = {"Authorization": "Bearer routine-secret"}


@pytest.fixture
def routine(monkeypatch, mocks, connected, slack_bot):
    monkeypatch.setattr(settings, "extraction_mode", "routine")
    monkeypatch.setattr(settings, "service_api_token", "routine-secret")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    return slack_bot


def answer_all(client, mocks, rewrite=None) -> int:
    """Play the routine: answer every waiting request the way the mock Claude would (optionally rewritten)."""
    jobs = client.get("/api/service/v1/llm-jobs?limit=20", headers=TOKEN).json()
    for job in jobs:
        prompt = "\n".join(m["content"] for m in job["messages"] if m["role"] == "user")
        if job["kind"] == "email":
            answer = mocks._email_for(job["messages"][0]["content"])
        else:
            answer = mocks._extraction_for(prompt)
        if rewrite:
            answer = rewrite(job, answer)
        resp = client.post(
            f"/api/service/v1/llm-jobs/{job['id']}/answer", headers=TOKEN, json={"text": json.dumps(answer)}
        )
        assert resp.status_code == 204, resp.text
    return len(jobs)


def statuses(db) -> dict[str, str]:
    with db() as s:
        return {m.title: m.status for m in s.scalars(select(Meeting))}


def test_the_service_api_needs_the_token(client, routine):
    assert client.get("/api/service/v1/llm-jobs").status_code == 401
    assert client.get("/api/service/v1/llm-jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_a_meeting_goes_from_queue_to_drafts(client, routine, mocks, db):
    with db() as s:
        record = run.run(s)
    assert record.error is None and record.processed == 0
    assert statuses(db) == {"Weekly revenue": "waiting", "Housekeeping sync": "waiting"}
    assert routine == []  # nothing to summarise yet

    queue = client.get("/api/service/v1/queue", headers=TOKEN).json()
    assert queue["pending"] == 2
    jobs = client.get("/api/service/v1/llm-jobs", headers=TOKEN).json()
    assert {j["kind"] for j in jobs} == {"extract"} and jobs[0]["schema"]["type"] == "object"
    assert "<notes>" in jobs[0]["messages"][0]["content"]

    assert answer_all(client, mocks) == 2
    assert client.post("/api/service/v1/run", headers=TOKEN).json()["processed"] == 1
    # Housekeeping has no external attendees, so it's done; Weekly revenue now waits for its email.
    assert statuses(db) == {"Weekly revenue": "waiting", "Housekeeping sync": "done"}
    assert len(routine) == 1 and "Housekeeping sync" in routine[0]["text"]

    assert answer_all(client, mocks) == 1  # the email
    assert client.post("/api/service/v1/run", headers=TOKEN).json()["processed"] == 1
    assert statuses(db) == {"Weekly revenue": "done", "Housekeeping sync": "done"}
    with db() as s:
        email = s.scalar(select(Output).where(Output.type == "email_draft"))
        assert email.status == "draft" and email.subject == "Follow-up: Weekly revenue"
    assert len(mocks.state["drafts"]) == 1
    assert "Weekly revenue" in routine[1]["text"]


def test_answers_are_checked_like_api_answers(client, routine, mocks, db):
    mocks.state["files"].pop("doc-revenue-weekly")
    with db() as s:
        run.run(s)

    def ungrounded(job, answer):
        answer["action_items"][0]["source_quote"] = "Russell promised a new boiler"
        return answer

    answer_all(client, mocks, ungrounded)
    client.post("/api/service/v1/run", headers=TOKEN)
    assert statuses(db) == {"Housekeeping sync": "waiting"}
    retry = client.get("/api/service/v1/llm-jobs", headers=TOKEN).json()
    assert len(retry) == 1 and [m["role"] for m in retry[0]["messages"]] == ["user", "assistant", "user"]
    assert "Russell promised a new boiler" in retry[0]["messages"][2]["content"]

    answer_all(client, mocks)
    client.post("/api/service/v1/run", headers=TOKEN)
    assert statuses(db) == {"Housekeeping sync": "done"}


def test_bad_json_is_refused(client, routine, db):
    with db() as s:
        run.run(s)
    job = client.get("/api/service/v1/llm-jobs", headers=TOKEN).json()[0]
    resp = client.post(f"/api/service/v1/llm-jobs/{job['id']}/answer", headers=TOKEN, json={"text": "Sure! Here it is"})
    assert resp.status_code == 422 and resp.json()["code"] == "not_json"
    fenced = client.post(
        f"/api/service/v1/llm-jobs/{job['id']}/answer", headers=TOKEN, json={"text": '```json\n{"a": 1}\n```'}
    )
    assert fenced.status_code == 204


def test_a_failed_request_uses_an_attempt_and_is_asked_again(client, routine, mocks, db):
    mocks.state["files"].pop("doc-revenue-weekly")
    with db() as s:
        run.run(s)
    job = client.get("/api/service/v1/llm-jobs", headers=TOKEN).json()[0]
    client.post(f"/api/service/v1/llm-jobs/{job['id']}/fail", headers=TOKEN, json={"reason": "Claude declined"})
    client.post("/api/service/v1/run", headers=TOKEN)
    with db() as s:
        meeting = s.scalar(select(Meeting))
        assert meeting.status == "queued" and "Claude declined" in meeting.error and meeting.attempts == 1
    client.post("/api/service/v1/run", headers=TOKEN)
    assert client.get("/api/service/v1/queue", headers=TOKEN).json()["pending"] == 1  # asked again
    assert statuses(db) == {"Housekeeping sync": "waiting"}


def test_answers_given_while_the_email_waits_are_kept(client, routine, mocks, db, sign_in):
    mocks.state["files"].pop("doc-housekeeping-sync")
    with db() as s:
        run.run(s)
    answer_all(client, mocks)
    client.post("/api/service/v1/run", headers=TOKEN)
    assert statuses(db) == {"Weekly revenue": "waiting"}  # on its email

    david = sign_in("david@liddellpropertyinvestments.com")
    question = david.get("/api/today").json()["questions"][0]
    sam = next(p["id"] for p in david.get("/api/people").json() if p["name"] == "Sam")
    david.post(f"/api/questions/{question['id']}/answer", json={"owner_user_id": sam})

    # The new owner changes the email's next steps, so the email is asked for again with it.
    answer_all(client, mocks)
    client.post("/api/service/v1/run", headers=TOKEN)
    assert statuses(db) == {"Weekly revenue": "waiting"}
    answer_all(client, mocks)
    client.post("/api/service/v1/run", headers=TOKEN)
    assert statuses(db) == {"Weekly revenue": "done"}
    assert david.get("/api/today").json()["counts"]["questions"] == 0  # the answer survived
    with db() as s:
        email = s.scalar(select(Output).where(Output.type == "email_draft"))
        assert "Check the Canary upsell settings for The Hearth (Sam)" in email.body


def test_old_requests_are_purged_with_the_notes(client, routine, db, monkeypatch):
    from datetime import timedelta

    from bide_followup import clock
    from tests.conftest import NOW

    with db() as s:
        run.run(s)
        assert s.query(LlmJob).count() == 2
        monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=31))
        run.purge_raw_text(s)
        assert s.query(LlmJob).count() == 0


def test_today_flags_a_routine_that_stopped(client, routine, db, sign_in, monkeypatch):
    from datetime import timedelta

    from bide_followup import clock
    from tests.conftest import NOW

    with db() as s:
        run.run(s)
    david = sign_in("david@liddellpropertyinvestments.com")
    assert david.get("/api/today").json()["problems"] == []
    monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(hours=4))
    with db() as s:
        run.run(s)  # still unanswered
    assert len(david.get("/api/today").json()["problems"]) == 2
    status = sign_in("kyle@bidehotels.com").get("/api/admin/claude").json()
    assert status["mode"] == "routine" and status["pending"] == 2 and status["enabled"]


def test_admin_connects_the_routine_from_the_app(client, sign_in, monkeypatch, db):
    monkeypatch.setattr(settings, "service_api_token", "")
    admin = sign_in("david@liddellpropertyinvestments.com")
    status = admin.get("/api/admin/claude").json()
    assert (status["mode"], status["routine_token_set"]) == ("api", False)
    assert "$FOLLOWUP_TOKEN" in status["routine_prompt"] and status["routine_schedule"]
    assert client.get("/api/service/v1/queue", headers=TOKEN).status_code == 503

    status = admin.put("/api/admin/claude/mode", json={"mode": "routine"}).json()
    assert (status["mode"], status["enabled"]) == ("routine", False)  # no token yet
    token = admin.post("/api/admin/claude/routine-token").json()["token"]
    with db() as s:
        assert token not in str(s.scalar(select(Setting).where(Setting.key == "routine_token_hash")).value)
    assert client.get("/api/service/v1/queue", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    status = admin.get("/api/admin/claude").json()
    assert status["enabled"] and status["routine_token_set"] and status["routine_seen_at"]

    second = admin.post("/api/admin/claude/routine-token").json()["token"]
    assert client.get("/api/service/v1/queue", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert admin.delete("/api/admin/claude/routine-token").status_code == 204
    assert client.get("/api/service/v1/queue", headers={"Authorization": f"Bearer {second}"}).status_code == 503
    assert sign_in("sam@bidehotels.com").post("/api/admin/claude/routine-token").status_code == 403
