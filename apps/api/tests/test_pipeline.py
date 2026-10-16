from datetime import date, timedelta

from sqlalchemy import select

from bide_followup.models import ActionItem, Meeting, Run, SkipRule, User
from bide_followup.pipeline import run
from tests.conftest import NOW


def meetings(db) -> dict[str, Meeting]:
    with db() as s:
        rows = s.scalars(select(Meeting)).all()
        for m in rows:
            _ = (m.attendees, m.action_items, m.questions)  # load before the session closes
        return {m.title: m for m in rows}


def test_run_extracts_each_new_note(db, mocks, connected):
    with db() as s:
        record = run.run(s)
    assert (record.found, record.processed, record.skipped, record.failed, record.error) == (2, 2, 0, 0, None)
    found = meetings(db)
    revenue = found["Weekly revenue"]
    assert revenue.status == "done" and revenue.calendar_event_id == "event-doc-revenue-weekly"
    assert revenue.properties == ["The View", "The Hearth"] and revenue.prompt_version == "extract_v2"
    assert revenue.input_tokens > 0 and revenue.raw_text and revenue.raw_text_expires_at
    # Attendees come from the invite (the meeting room left out); internal by domain or the people list.
    assert sorted((a.name, a.is_internal) for a in revenue.attendees) == [
        ("David", True),
        ("Priya Shah", False),
        ("Sam", True),
    ]
    with db() as s:
        sam = s.scalar(select(User).where(User.name == "Sam"))
        actions = {a.description: a for a in s.scalars(select(ActionItem).where(ActionItem.meeting_id == revenue.id))}
    pricelabs = actions["Update the PriceLabs minimum-stay rule for The View to two nights"]
    assert pricelabs.owner_user_id == sam.id and pricelabs.due_date == date(2026, 10, 16)
    priya = actions["Send David the comparison report for Highland short stays"]
    assert priya.owner_name == "Priya Shah" and priya.owner_status == "assigned" and priya.due_date is None
    canary = actions["Check the Canary upsell settings for The Hearth"]
    assert canary.owner_status == "needs_david"
    assert [q.action_item_id for q in revenue.questions] == [canary.id]


def test_second_run_does_nothing_new(db, mocks, connected):
    with db() as s:
        run.run(s)
        record = run.run(s)
        assert (record.found, record.processed) == (2, 0)
        assert s.query(Meeting).count() == 2
        assert s.query(Run).count() == 2


def test_notes_still_being_written_wait(db, mocks, connected):
    for f in mocks.state["files"].values():
        f["modified"] = NOW - timedelta(minutes=5)
    with db() as s:
        record = run.run(s)
        assert record.found == 2 and s.query(Meeting).count() == 0


def test_skip_rules(db, mocks, connected):
    with db() as s:
        s.add_all(
            [
                SkipRule(type="title_keyword", value="housekeeping"),
                SkipRule(type="attendee_email", value="priya@pricelabs.example"),
            ]
        )
        s.commit()
        record = run.run(s)
    assert (record.processed, record.skipped) == (0, 2)
    found = meetings(db)
    assert found["Housekeeping sync"].skip_reason == "Title contains “housekeeping”"
    assert found["Weekly revenue"].skip_reason == "Attendee priya@pricelabs.example is on the skip list"
    assert found["Weekly revenue"].action_items == []


def test_not_connected_pauses(db, mocks):
    with db() as s:
        record = run.run(s)
    assert record.error.startswith("Paused") and record.found == 0


def test_without_api_key_meetings_wait(db, mocks, connected, monkeypatch):
    from bide_followup.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with db() as s:
        record = run.run(s)
    assert record.processed == 0 and "ANTHROPIC_API_KEY" in record.error
    assert {m.status for m in meetings(db).values()} == {"queued"}


def test_failures_retry_then_fail(db, mocks, connected, monkeypatch):
    from bide_followup.pipeline import extract

    def broken(*args, **kwargs):
        raise extract.ExtractionFailed("bad JSON")

    monkeypatch.setattr(extract, "extract", broken)
    with db() as s:
        statuses = []
        for _ in range(3):
            record = run.run(s)
            statuses.append((record.failed, sorted(m.status for m in s.scalars(select(Meeting)))))
    assert statuses == [(0, ["queued", "queued"]), (0, ["queued", "queued"]), (2, ["failed", "failed"])]
    assert all(m.error == "ExtractionFailed: bad JSON" for m in meetings(db).values())


def test_purge_raw_text(db, mocks, connected, monkeypatch):
    from bide_followup import clock

    with db() as s:
        run.run(s)
        assert run.purge_raw_text(s) == 0
        monkeypatch.setattr(clock, "now", lambda: NOW + timedelta(days=31))
        assert run.purge_raw_text(s) == 2
        assert all(m.raw_text is None for m in s.scalars(select(Meeting)))


def test_run_now_endpoint(sign_in, mocks, connected):
    client = sign_in("kyle@bidehotels.com")
    assert client.post("/api/admin/runs").json()["processed"] == 2
    assert len(client.get("/api/admin/runs").json()) == 1


def test_claude_request_shape(db, mocks, connected):
    with db() as s:
        run.run(s)
    sent = mocks.state["last_request"]
    body = sent["body"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in sent["beta"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == "medium"
    assert "Russell (russell@bidehotels.com), member; owns operations, housekeeping" in body["system"]
    assert body["messages"][-1]["role"] == "user" and "<notes>" in body["messages"][-1]["content"]


def test_extraction_retries_once_with_the_problems(db, mocks, connected, monkeypatch):
    import json

    from bide_followup.integrations import llm
    from mocks.samples import SAMPLES

    good = json.loads(json.dumps(SAMPLES[1]["extraction"]))
    bad = json.loads(json.dumps(good))
    bad["action_items"][0]["source_quote"] = "Russell promised a new boiler"
    calls = []

    def complete(system, messages, schema, **kwargs):
        calls.append(messages)
        answer = bad if len(calls) % 2 else good
        return llm.Completion(text=json.dumps(answer), model="m", input_tokens=10, output_tokens=5)

    monkeypatch.setattr(llm, "complete", complete)
    mocks.state["files"].pop("doc-revenue-weekly")
    with db() as s:
        run.run(s)
        meeting = s.scalar(select(Meeting))
        assert meeting.status == "done" and meeting.input_tokens == 20
        assert len(meeting.action_items) == 2 and meeting.extraction["dropped_actions"] == []
    retry = calls[1]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert "Russell promised a new boiler" in retry[2]["content"]
