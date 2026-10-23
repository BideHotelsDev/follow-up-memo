from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from bide_followup import runtime_settings
from bide_followup.models import ActionItem, Meeting, Notice, Output, Question, User
from bide_followup.pipeline import notices

UK = ZoneInfo("Europe/London")
TUESDAY_9AM = datetime(2026, 10, 13, 9, 0, tzinfo=UK)
MONDAY_9AM = datetime(2026, 10, 19, 9, 0, tzinfo=UK)


@pytest.fixture
def tasks(db):
    """Sam: one overdue, one due today, one due tomorrow, one done. Russell: nothing due."""
    with db() as s:
        sam = s.scalar(select(User).where(User.name == "Sam"))
        russell = s.scalar(select(User).where(User.name == "Russell"))
        m = Meeting(
            drive_file_id="d1",
            title="Weekly revenue",
            started_at=datetime(2026, 10, 8, 10, tzinfo=UK),
            status="done",
        )
        today = TUESDAY_9AM.date()
        for text, due, status in [
            ("Send the rate sheet", today - timedelta(days=2), "open"),
            ("Update PriceLabs", today, "open"),
            ("Book the photographer", today + timedelta(days=1), "open"),
            ("Old one", today - timedelta(days=5), "done"),
        ]:
            m.action_items.append(
                ActionItem(description=text, owner_user_id=sam.id, owner_status="assigned", due_date=due, status=status)
            )
        m.action_items.append(
            ActionItem(description="Fix Operto", owner_user_id=russell.id, owner_status="assigned", due_date=None)
        )
        s.add(m)
        s.commit()


def switch_on(db, **values):
    with db() as s:
        for key, value in values.items():
            runtime_settings.put(s, key, value)
        s.commit()


def test_reminders_go_to_people_with_tasks_due(db, slack_bot, tasks):
    switch_on(db, reminders_enabled=True)
    with db() as s:
        notices.send_due(s, TUESDAY_9AM)
    assert [m["channel"] for m in slack_bot] == ["D-U0SAM"]
    text = slack_bot[0]["text"]
    assert text.startswith("*Good morning, Sam.* 2 tasks from meetings need you:")
    assert "*Overdue*\n• Send the rate sheet (due Sun 11 Oct, from Weekly revenue)" in text
    assert "*Due today*\n• Update PriceLabs (from Weekly revenue)" in text
    assert "Book the photographer" not in text and "Old one" not in text

    with db() as s:
        notices.send_due(s, TUESDAY_9AM + timedelta(minutes=10))  # the next check: already sent today
    assert len(slack_bot) == 1


@pytest.mark.parametrize(
    "moment, enabled",
    [
        (TUESDAY_9AM, False),  # switched off (the default)
        (datetime(2026, 10, 13, 7, 0, tzinfo=UK), True),  # before the set hour
        (datetime(2026, 10, 13, 15, 0, tzinfo=UK), True),  # long after it: no afternoon reminders after an outage
        (datetime(2026, 10, 17, 9, 0, tzinfo=UK), True),  # Saturday
    ],
)
def test_no_reminders_outside_the_schedule(db, slack_bot, tasks, moment, enabled):
    switch_on(db, reminders_enabled=enabled, weekly_digest_enabled=False)
    with db() as s:
        notices.send_due(s, moment)
    assert slack_bot == []


def test_a_reminder_that_cannot_be_sent_is_retried(db, slack_bot, tasks):
    with db() as s:
        sam = s.scalar(select(User).where(User.name == "Sam"))
        sam.slack_user_id = None  # and Slack doesn't know his email
        s.commit()
        notices.send_reminders(s, TUESDAY_9AM.date())
        row = s.scalar(select(Notice))
        assert (row.status, row.error) == ("failed", "Sam has no Slack member ID (Admin → People)")
        sam.slack_user_id = "U0SAM"
        s.commit()
        notices.send_reminders(s, TUESDAY_9AM.date())
        assert (row.status, row.attempts, row.recipient) == ("posted", 2, "U0SAM")
    assert len(slack_bot) == 1


def test_the_weekly_digest(db, slack_bot, tasks):
    with db() as s:
        meeting = s.scalar(select(Meeting))
        late, on_time = (
            ActionItem(description="A", owner_status="needs_david", due_date=date(2026, 10, 13), status="done"),
            ActionItem(description="B", owner_status="needs_david", due_date=None, status="done"),
        )
        late.done_at = datetime(2026, 10, 15, 12, tzinfo=UK)
        on_time.done_at = datetime(2026, 10, 14, 12, tzinfo=UK)
        meeting.action_items += [late, on_time]
        meeting.questions.append(Question(text="Who books the clean?"))
        meeting.outputs.append(Output(type="email_draft", recipient="a@b.example", body="x", status="draft"))
        s.commit()
        notices.send_due(s, MONDAY_9AM)
        notices.send_due(s, MONDAY_9AM + timedelta(hours=1))
    assert [m["channel"] for m in slack_bot] == ["D-U0DAVID"]
    text = slack_bot[0]["text"]
    assert text.startswith("*David’s week in follow-ups* (Mon 12 Oct – Sun 18 Oct)")
    assert "• 1 meeting processed" not in text  # the meeting started before the week
    assert "• 0 meetings processed" in text
    assert "• 2 actions done: 1 on time, 1 late" in text
    # Sam's three open tasks are all past due by Monday 19th; Russell's has no date.
    assert "• 3 tasks overdue now: 3 Sam" in text
    assert "    – Send the rate sheet (Sam, due Sun 11 Oct)" in text
    assert "• Waiting for you: 1 question, 1 email draft" in text


def test_digest_waits_for_its_day_and_can_be_switched_off(db, slack_bot, tasks):
    with db() as s:
        notices.send_due(s, TUESDAY_9AM)
    assert slack_bot == []
    switch_on(db, weekly_digest_enabled=False)
    with db() as s:
        notices.send_due(s, MONDAY_9AM)
    assert slack_bot == []


def test_admin_previews_and_log(sign_in, db, slack_bot, tasks, monkeypatch):
    client = sign_in("david@liddellpropertyinvestments.com")
    assert client.get("/api/admin/digest-preview").json()["text"].startswith("*David’s week in follow-ups*")
    assert "no reminder for David" in client.get("/api/admin/reminder-preview").json()["text"]
    assert slack_bot == []  # previews send nothing
    resp = client.put("/api/admin/settings", json={"reminders_enabled": True, "reminder_hour": 9})
    assert resp.json()["reminders_enabled"] and client.get("/api/app").json()["pipeline"]["reminder_hour"] == 9
    assert client.put("/api/admin/settings", json={"reminder_hour": 23}).status_code == 422
    with db() as s:
        notices.send_due(s, TUESDAY_9AM)
    log = client.get("/api/admin/notices").json()
    assert [(n["kind"], n["person"], n["status"]) for n in log] == [("reminder", "Sam", "posted")]
    assert sign_in("sam@bidehotels.com").get("/api/admin/notices").status_code == 403


def test_undated_tasks_get_a_weekly_nudge(db, slack_bot, tasks):
    with db() as s:
        russell = s.scalar(select(User).where(User.name == "Russell"))
        text = notices.undated_text(s, russell, MONDAY_9AM.date())
        assert "Fix Operto" in text and "no due date" in text and "/tasks" in text
        sam = s.scalar(select(User).where(User.name == "Sam"))
        assert notices.undated_text(s, sam, MONDAY_9AM.date()) is None  # all of Sam's open tasks have dates

    switch_on(db, undated_nudge_enabled=True)
    with db() as s:
        notices.send_due(s, TUESDAY_9AM + timedelta(days=1))  # not the chosen day: nothing
        assert s.scalars(select(Notice).where(Notice.kind == "undated_nudge")).all() == []
        notices.send_due(s, MONDAY_9AM)
        notices.send_due(s, MONDAY_9AM + timedelta(hours=1))  # a second check that morning sends nothing new
        rows = s.scalars(select(Notice).where(Notice.kind == "undated_nudge")).all()
        assert [r.user.name for r in rows] == ["Russell"]


def test_the_undated_nudge_starts_switched_off(db, slack_bot, tasks):
    with db() as s:
        notices.send_due(s, MONDAY_9AM)
        assert s.scalars(select(Notice).where(Notice.kind == "undated_nudge")).all() == []
