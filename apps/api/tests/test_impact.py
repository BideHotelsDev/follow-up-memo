from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from bide_followup.models import ActionItem, Meeting, Output, Run, User
from tests.conftest import NOW

LONDON = ZoneInfo("Europe/London")


@pytest.fixture
def history(db):
    """Three weeks of meetings: followed up fast, followed up slowly, never followed up, failed, and an internal
    call with nothing to follow up (left out)."""
    with db() as s:
        people = {u.name: u for u in s.scalars(select(User))}

        def meeting(title, start, props, status="done", outputs=(), actions=()):
            m = Meeting(
                drive_file_id=title,
                title=title,
                started_at=start,
                ended_at=start + timedelta(minutes=30),
                properties=props,
                status=status,
            )
            for type_, out_status, acted_after in outputs:
                o = Output(type=type_, recipient=f"{title}-{type_}", body="x", status=out_status, attempts=0)
                o.created_at = start + timedelta(minutes=45)
                if acted_after is not None:
                    o.approved_at = start + timedelta(minutes=30) + acted_after
                m.outputs.append(o)
            for owner, due, task_status, done_at in actions:
                m.action_items.append(
                    ActionItem(
                        description=f"{title} {owner}",
                        owner_user_id=people[owner].id if owner in people else None,
                        owner_name=None if owner in people else owner,
                        owner_status="assigned",
                        due_date=due,
                        status=task_status,
                        done_at=done_at,
                    )
                )
            s.add(m)

        week0 = NOW - timedelta(days=14)
        meeting(
            "Fast",
            week0,
            ["The View"],
            outputs=[("slack_dm", "posted", timedelta(hours=2))],
            actions=[("Sam", date(2026, 10, 1), "done", datetime(2026, 9, 30, 12, tzinfo=LONDON))],
        )
        meeting(
            "Slow",
            week0 + timedelta(days=1),
            ["The View"],
            outputs=[("email_draft", "closed_in_gmail", timedelta(hours=30))],
            actions=[("Russell", date(2026, 10, 2), "done", datetime(2026, 10, 5, 12, tzinfo=LONDON))],
        )
        meeting(
            "Ignored",
            NOW - timedelta(days=2),
            ["The Villa"],
            outputs=[("slack_digest", "draft", None)],
            actions=[("Russell", date(2026, 10, 12), "open", None), ("Priya", None, "open", None)],
        )
        meeting("Broken", NOW - timedelta(days=1), [], status="failed")
        meeting("Internal", NOW - timedelta(days=1), ["The View"])
        meeting("Skipped", NOW - timedelta(days=1), ["The View"], status="skipped")
        s.add_all(
            [
                Run(started_at=NOW - timedelta(days=3), processed=2),
                Run(started_at=NOW - timedelta(days=1), error="Google disconnected"),
                Run(started_at=NOW - timedelta(days=60)),  # before the period
            ]
        )
        s.commit()


def test_impact_numbers(sign_in, history):
    client = sign_in("david@liddellpropertyinvestments.com")
    data = client.get("/api/impact?weeks=4").json()
    assert data["since"] == "2026-09-21"
    assert (data["meetings"], data["followed_up"], data["followed_up_rate"]) == (4, 1, 25)
    assert [(w["meetings"], w["followed_up"]) for w in data["weeks"]] == [(0, 0), (2, 1), (1, 0), (1, 0)]
    assert data["weeks"][-1]["in_progress"] and data["weeks"][0]["rate"] is None
    assert data["minutes_to_drafts"] == 15.0
    assert data["minutes_to_follow_up"] == 960.0  # (2 h + 30 h) / 2
    assert data["actions"] == {"on_time": 1, "late": 1, "open": 1, "overdue": 1, "on_time_rate": 50}
    assert {o["name"]: (o["open"], o["overdue"]) for o in data["owners"]} == {"Russell": (0, 1), "External": (1, 0)}
    assert data["drafts"] == {"acted": 2, "unedited": 2, "reassigned": 0, "actions": 4}
    assert data["meetings_handled"] == 4  # Fast, Slow, Ignored, Internal: everything the app read
    hotels = {h["name"]: h for h in data["hotels"]}
    assert hotels["The View"]["followed_up_rate"] == 50 and hotels["The View"]["on_time_rate"] == 50
    assert hotels["Bide-wide"]["meetings"] == 1 and hotels["Bide-wide"]["followed_up_rate"] == 0

    system = data["system"]
    assert (system["runs"], system["runs_ok"]) == (2, 1) and system["last_failed_run_at"]
    assert (system["meetings_read"], system["meetings_failed"], system["meetings_skipped"]) == (4, 1, 1)
    assert (system["emails_drafted"], system["slack_drafted"], system["slack_posted"]) == (1, 2, 1)
    assert [(w["read"], w["failed"], w["skipped"]) for w in system["weeks"]] == [
        (0, 0, 0),
        (2, 0, 0),
        (1, 0, 0),
        (1, 1, 1),
    ]


def test_hotel_filter_and_reassignments_and_edits(sign_in, history, db, slack_bot):
    client = sign_in("david@liddellpropertyinvestments.com")
    villa = client.get("/api/impact?property=The Villa").json()
    assert villa["meetings"] == 1 and villa["hotels"] == []

    with db() as s:
        slack = s.scalar(select(Output).where(Output.type == "slack_digest"))
    client.patch(f"/api/outputs/{slack.id}", json={"body": "edited"})
    client.post(f"/api/outputs/{slack.id}/approve")
    task = next(t for t in client.get("/api/tasks").json() if t["description"] == "Ignored Russell")
    sam = next(p["id"] for p in client.get("/api/people").json() if p["name"] == "Sam")
    client.patch(f"/api/tasks/{task['id']}", json={"owner_user_id": sam})
    data = client.get("/api/impact").json()
    assert data["drafts"]["reassigned"] == 1
    assert data["drafts"]["acted"] == 3 and data["drafts"]["unedited"] == 2
    assert data["david_active_days"] == 1


def test_ticking_a_task_records_when(sign_in, history, monkeypatch):
    client = sign_in("david@liddellpropertyinvestments.com")
    task = next(t for t in client.get("/api/tasks").json() if t["description"] == "Ignored Russell")
    client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    late = client.get("/api/impact").json()["actions"]
    assert late["late"] == 2 and late["overdue"] == 0  # due 12 Oct, done 13 Oct
    client.patch(f"/api/tasks/{task['id']}", json={"status": "open"})
    assert client.get("/api/impact").json()["actions"]["overdue"] == 1


def test_baselines_and_minutes(sign_in):
    client = sign_in("kyle@bidehotels.com")
    client.put("/api/admin/settings", json={"baseline_followup_rate": 20, "baseline_followup_days": 3.5})
    client.put("/api/admin/settings", json={"minutes_saved_per_meeting": 25})
    data = client.get("/api/impact").json()
    assert (data["baseline_followup_rate"], data["baseline_followup_days"], data["minutes_saved_per_meeting"]) == (
        20,
        3.5,
        25,
    )
    client.put("/api/admin/settings", json={"baseline_followup_rate": None})
    assert client.get("/api/impact").json()["baseline_followup_rate"] is None


def test_members_cant_see_impact(sign_in):
    assert sign_in("sam@bidehotels.com").get("/api/impact").status_code == 403
