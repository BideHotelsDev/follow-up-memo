from datetime import date

import pytest
from sqlalchemy import select

from bide_followup.models import AuditLog, ChannelMap, Meeting, Output, User
from bide_followup.pipeline import run


@pytest.fixture
def processed(db, mocks, connected, slack_bot):
    """Both sample meetings run through the pipeline, with channels mapped and Sam's Slack ID known."""
    with db() as s:
        s.add_all(
            [
                ChannelMap(category="Revenue", slack_channel_id="C0REVENUE", slack_channel_name="revenue"),
                ChannelMap(property="The Villa", slack_channel_id="C0VILLA", slack_channel_name="the-villa"),
            ]
        )
        s.commit()
        run.run(s)
    slack_bot.clear()  # the run summary
    return slack_bot


def ids(db) -> dict:
    with db() as s:
        users = {u.name: str(u.id) for u in s.scalars(select(User))}
        meetings = {m.title: str(m.id) for m in s.scalars(select(Meeting))}
    return {**users, **meetings}


def test_members_see_only_their_own_tasks(sign_in, processed, db):
    client = sign_in("sam@bidehotels.com")
    assert client.get("/api/meetings").status_code == 403
    assert client.get("/api/outputs").status_code == 403
    tasks = client.get("/api/tasks").json()
    assert [t["owner"]["name"] for t in tasks] == ["Sam"]
    today = client.get("/api/today").json()
    assert today["counts"]["tasks_open"] == 1 and today["meetings"] == [] and today["questions"] == []
    russell = ids(db)["Russell"]
    assert [t["owner"]["name"] for t in client.get(f"/api/tasks?owner={russell}").json()] == ["Sam"]  # still own


def test_today_for_david(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    today = client.get("/api/today").json()
    assert today["date"] == "2026-10-13" and [m["title"] for m in today["meetings"]] == [
        "Weekly revenue",
        "Housekeeping sync",
    ]
    assert today["counts"] == {"questions": 2, "emails": 1, "slack": 4, "tasks_open": 1, "tasks_overdue": 0}
    assert today["last_run"]["processed"] == 2
    villa = client.get("/api/today?property=The Villa").json()
    assert [m["title"] for m in villa["meetings"]] == ["Housekeeping sync"]


def test_meetings_by_person(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    people = ids(db)
    by = lambda name: [m["title"] for m in client.get(f"/api/meetings?person={people[name]}").json()]
    assert by("Sam") == ["Weekly revenue"]  # attended, and owns an action
    assert by("Russell") == ["Housekeeping sync"]
    assert by("David") == ["Housekeeping sync", "Weekly revenue"]
    assert by("Kyle") == []


def test_meeting_detail(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    meetings = client.get("/api/meetings").json()
    assert [m["title"] for m in meetings] == ["Housekeeping sync", "Weekly revenue"]  # newest first
    detail = client.get(f"/api/meetings/{ids(db)['Weekly revenue']}").json()
    assert detail["decisions"] == ["Lower the minimum stay at The View to two nights for half-term."]
    assert detail["notes_url"].endswith("doc-revenue-weekly/edit")
    assert {o["type"] for o in detail["outputs"]} == {"email_draft", "slack_dm", "slack_digest"}
    digest = next(o for o in detail["outputs"] if o["type"] == "slack_digest")
    assert digest["recipient_label"] == "#revenue"
    email = next(o for o in detail["outputs"] if o["type"] == "email_draft")
    assert email["gmail_url"].startswith("https://mail.google.com/")


def test_approve_posts_and_is_audited(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    drafts = client.get("/api/outputs?type=slack_dm").json()
    sam = next(o for o in drafts if o["recipient_label"] == "Sam")
    resp = client.post(f"/api/outputs/{sam['id']}/approve")
    assert resp.json()["status"] == "posted"
    assert [m["channel"] for m in processed] == ["D-U0SAM"]
    assert client.post(f"/api/outputs/{sam['id']}/approve").json()["code"] == "not_a_draft"
    with db() as s:
        log = s.scalar(select(AuditLog).where(AuditLog.action == "approve"))
        assert log.user_id is not None and log.after == {"status": "posted"}


def test_emails_are_never_approved_here(sign_in, processed):
    client = sign_in("david@liddellpropertyinvestments.com")
    email = client.get("/api/outputs?type=email_draft").json()[0]
    assert client.post(f"/api/outputs/{email['id']}/approve").json()["code"] == "not_slack"


def test_approve_all_for_a_meeting(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    resp = client.post("/api/outputs/approve-all", json={"meeting_id": ids(db)["Weekly revenue"]})
    assert sorted(o["recipient_label"] for o in resp.json()) == ["#revenue", "Sam"]
    assert sorted(m["channel"] for m in processed) == ["C0REVENUE", "D-U0SAM"]
    waiting = client.get("/api/outputs?type=slack_dm&status=draft").json()
    assert [o["recipient_label"] for o in waiting] == ["Russell"]


def test_edit_email_updates_gmail(sign_in, processed, mocks):
    client = sign_in("david@liddellpropertyinvestments.com")
    email = client.get("/api/outputs?type=email_draft").json()[0]
    resp = client.patch(f"/api/outputs/{email['id']}", json={"subject": "Thanks, Priya", "body": "Hi Priya, thanks."})
    assert resp.json()["subject"] == "Thanks, Priya"
    draft = next(iter(mocks.state["drafts"].values()))
    assert draft["subject"] == "Thanks, Priya" and draft["body"].strip() == "Hi Priya, thanks."


def test_discard_email_deletes_the_gmail_draft(sign_in, processed, mocks):
    client = sign_in("david@liddellpropertyinvestments.com")
    email = client.get("/api/outputs?type=email_draft").json()[0]
    assert client.post(f"/api/outputs/{email['id']}/discard").json()["status"] == "discarded"
    assert mocks.state["drafts"] == {}
    assert client.get("/api/outputs?type=email_draft").json() == []


def test_answering_an_owner_question_assigns_the_task_and_drafts_a_dm(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    question = next(q for q in client.get("/api/today").json()["questions"] if q["kind"] == "owner")
    resp = client.post(f"/api/questions/{question['id']}/answer", json={"owner_user_id": ids(db)["Sam"]})
    assert resp.json()["answer"] == "Sam"
    sam_dm = next(o for o in client.get("/api/outputs?type=slack_dm").json() if o["recipient_label"] == "Sam")
    assert "Canary upsell" in sam_dm["body"]
    assert client.get("/api/today").json()["counts"]["questions"] == 1
    client.post(f"/api/questions/{question['id']}/reopen")
    assert client.get("/api/today").json()["counts"]["questions"] == 2


def test_a_dictated_answer_keeps_its_lines(sign_in, processed):
    client = sign_in("david@liddellpropertyinvestments.com")
    question = next(q for q in client.get("/api/today").json()["questions"] if q["kind"] == "other")
    text = "Yes, from the week before.\nAsk Russell to tell the laundry."
    assert client.post(f"/api/questions/{question['id']}/answer", json={"text": text}).json()["answer"] == text


def test_task_edits(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    tasks = client.get("/api/tasks").json()
    buckets = {t["description"]: t["bucket"] for t in tasks}
    assert buckets["Update the PriceLabs minimum-stay rule for The View to two nights"] == "week"
    assert buckets["Ask the laundry about a second delivery day"] == "nodate"
    assert len(client.get("/api/tasks?owner=needs_david").json()) == 1
    assert [t["owner_name"] for t in client.get("/api/tasks?owner=external").json()] == ["Priya Shah"]

    laundry = next(t for t in tasks if t["description"].startswith("Ask the laundry"))
    resp = client.patch(f"/api/tasks/{laundry['id']}", json={"due_date": "2026-10-12"})
    assert resp.json()["bucket"] == "late"
    resp = client.patch(f"/api/tasks/{laundry['id']}", json={"owner_user_id": None})
    assert resp.json()["owner_status"] == "needs_david" and resp.json()["owner"] is None
    assert client.patch(f"/api/tasks/{laundry['id']}", json={"status": "done"}).json()["bucket"] == "done"


def test_members_can_only_tick_their_own_tasks(sign_in, processed, db):
    client = sign_in("sam@bidehotels.com")
    mine = client.get("/api/tasks").json()[0]
    assert client.patch(f"/api/tasks/{mine['id']}", json={"status": "done"}).json()["status"] == "done"
    assert client.patch(f"/api/tasks/{mine['id']}", json={"due_date": "2026-10-20"}).status_code == 403
    with db() as s:
        russells = s.scalar(select(User).where(User.name == "Russell"))
        other = next(a for m in s.scalars(select(Meeting)) for a in m.action_items if a.owner_user_id == russells.id)
    assert client.patch(f"/api/tasks/{other.id}", json={"status": "done"}).status_code == 404


def test_reprocess_keeps_approved_drafts(sign_in, processed, db):
    client = sign_in("david@liddellpropertyinvestments.com")
    revenue = ids(db)["Weekly revenue"]
    client.post("/api/outputs/approve-all", json={"meeting_id": revenue})
    detail = client.post(f"/api/meetings/{revenue}/reprocess").json()
    assert detail["status"] == "done" and len(detail["tasks"]) == 3
    statuses = sorted((o["type"], o["status"]) for o in detail["outputs"])
    assert statuses == [("email_draft", "draft"), ("slack_digest", "posted"), ("slack_dm", "posted")]


def test_gmail_sync_closes_sent_drafts(db, processed, mocks):
    from bide_followup.pipeline import outputs

    mocks.state["drafts"].clear()  # David sent (or deleted) it in Gmail
    with db() as s:
        assert outputs.sync_gmail(s) == 1
        assert s.scalar(select(Output).where(Output.type == "email_draft")).status == "closed_in_gmail"


def test_bucket_edges():
    from bide_followup.models import ActionItem
    from bide_followup.views import bucket

    today = date(2026, 10, 13)
    assert bucket(ActionItem(status="open", due_date=date(2026, 10, 19)), today) == "week"
    assert bucket(ActionItem(status="open", due_date=date(2026, 10, 20)), today) == "later"
    assert bucket(ActionItem(status="dismissed", due_date=None), today) == "done"
