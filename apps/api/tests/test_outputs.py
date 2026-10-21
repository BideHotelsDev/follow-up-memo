import inspect

import pytest
from sqlalchemy import select

from bide_followup.integrations import gmail
from bide_followup.models import ChannelMap, Meeting, Output, Run, User
from bide_followup.pipeline import run
from mocks.samples import SAMPLES


@pytest.fixture
def channels(db):
    with db() as s:
        s.add_all(
            [
                ChannelMap(category="Revenue", slack_channel_id="C0REVENUE"),
                ChannelMap(property="The Villa", slack_channel_id="C0VILLA"),
            ]
        )
        s.commit()


def outputs(db) -> dict[tuple[str, str], Output]:
    with db() as s:
        return {(o.type, o.recipient): o for o in s.scalars(select(Output))}


def by_title(db, title: str) -> Meeting:
    with db() as s:
        return s.scalar(select(Meeting).where(Meeting.title == title))


def test_a_run_drafts_everything_and_only_posts_the_summary(db, mocks, connected, slack_bot, channels):
    with db() as s:
        run.run(s)
    out = outputs(db)
    assert sorted(out) == [
        ("email_draft", "priya@pricelabs.example"),
        ("run_summary", "U0DAVID"),
        ("slack_digest", "C0REVENUE"),
        ("slack_digest", "C0VILLA"),
        ("slack_dm", "U0RUSSELL"),
        ("slack_dm", "U0SAM"),
    ]
    email = out[("email_draft", "priya@pricelabs.example")]
    assert email.status == "draft" and email.subject == "Follow-up: Weekly revenue"
    assert mocks.state["drafts"][email.external_id]["to"] == "priya@pricelabs.example"
    # Slack drafts wait for approval; the run summary to David is the one message posted.
    assert all(o.status == "draft" for k, o in out.items() if k[0] in ("slack_dm", "slack_digest"))
    assert [m["channel"] for m in slack_bot] == ["D-U0DAVID"]
    summary = slack_bot[0]["text"]
    assert "2 meetings followed up" in summary and "Weekly revenue" in summary and "Gmail draft ready" in summary
    assert out[("run_summary", "U0DAVID")].status == "posted"
    sam_dm = out[("slack_dm", "U0SAM")].body
    assert "Update the PriceLabs minimum-stay rule" in sam_dm and "due Fri 16 Oct" in sam_dm
    assert "Canary" not in sam_dm  # only Sam's own actions
    assert {m.status for m in (by_title(db, "Weekly revenue"), by_title(db, "Housekeeping sync"))} == {"done"}
    with db() as s:
        assert s.scalar(select(User).where(User.role == "owner")).slack_user_id == "U0DAVID"


def test_internal_only_meeting_gets_no_email(db, mocks, connected, slack_bot):
    with db() as s:
        run.run(s)
    housekeeping = by_title(db, "Housekeeping sync")
    with db() as s:
        types = {o.type for o in s.scalars(select(Output).where(Output.meeting_id == housekeeping.id))}
    assert types == {"slack_dm"}  # no externals, and no channel mapped in this test


def test_sensitive_meeting_gets_no_team_messages(db, mocks, connected, slack_bot, channels, monkeypatch):
    monkeypatch.setitem(SAMPLES[0]["extraction"]["meeting"], "is_sensitive", True)
    with db() as s:
        run.run(s)
    revenue = by_title(db, "Weekly revenue")
    with db() as s:
        rows = s.scalars(select(Output).where(Output.meeting_id == revenue.id)).all()
    assert [(o.type, o.review_carefully) for o in rows] == [("email_draft", True)]
    assert "review carefully" in slack_bot[0]["text"] and "sensitive" in slack_bot[0]["text"]


def test_runs_are_idempotent(db, mocks, connected, slack_bot, channels):
    with db() as s:
        run.run(s)
        run.run(s)
        assert s.query(Output).count() == 6
    assert len(mocks.state["drafts"]) == 1 and len(slack_bot) == 1  # no second summary: nothing new


def test_regenerating_updates_drafts_and_leaves_settled_ones(db, mocks, connected, slack_bot, channels):
    from bide_followup.pipeline import outputs as pipeline_outputs

    with db() as s:
        run.run(s)
        sam = s.scalar(select(Output).where(Output.recipient == "U0SAM"))
        sam.status, sam.body = "approved", "edited by David"
        s.commit()
        meeting = s.scalar(select(Meeting).where(Meeting.title == "Weekly revenue"))
        pipeline_outputs.generate(s, meeting)
        s.commit()
        assert s.scalar(select(Output).where(Output.recipient == "U0SAM")).body == "edited by David"
        assert s.query(Output).filter_by(type="email_draft").count() == 1
    assert len(mocks.state["drafts"]) == 1  # the same Gmail draft, updated


def test_gmail_failure_makes_the_meeting_partial_and_retries(db, mocks, connected, slack_bot, monkeypatch):
    real = gmail.create_draft

    def down(*args, **kwargs):
        raise gmail.GmailError(503, "UNAVAILABLE")

    monkeypatch.setattr(gmail, "create_draft", down)
    with db() as s:
        run.run(s)
    assert by_title(db, "Weekly revenue").status == "partial"
    email = outputs(db)[("email_draft", "priya@pricelabs.example")]
    assert email.status == "failed" and "503" in email.error
    assert "some drafts failed" in slack_bot[0]["text"]

    monkeypatch.setattr(gmail, "create_draft", real)
    with db() as s:
        run.run(s)
    assert by_title(db, "Weekly revenue").status == "done"
    assert outputs(db)[("email_draft", "priya@pricelabs.example")].status == "draft"


def test_email_writing_failure_is_retried(db, mocks, connected, slack_bot, monkeypatch):
    from bide_followup.integrations import llm
    from bide_followup.pipeline import outputs as pipeline_outputs

    real = llm.complete

    def declined(system, messages, schema, **kwargs):
        if schema is pipeline_outputs.EMAIL_SCHEMA:
            raise llm.LlmError("declined")
        return real(system, messages, schema, **kwargs)

    monkeypatch.setattr(llm, "complete", declined)
    with db() as s:
        run.run(s)
    email = outputs(db)[("email_draft", "priya@pricelabs.example")]
    assert email.status == "failed" and email.body == ""
    assert by_title(db, "Weekly revenue").status == "partial"

    monkeypatch.setattr(llm, "complete", real)
    with db() as s:
        run.run(s)
    assert outputs(db)[("email_draft", "priya@pricelabs.example")].status == "draft"
    assert by_title(db, "Weekly revenue").status == "done"


def test_summary_fails_visibly_without_davids_slack_id(db, mocks, connected, slack_bot):
    mocks.SLACK_USERS.clear()
    with db() as s:
        run.run(s)
    summary = outputs(db)[("run_summary", "")]
    assert summary.status == "failed" and "Slack member ID" in summary.error
    mocks.SLACK_USERS["david@liddellpropertyinvestments.com"] = "U0DAVID"


def test_admin_alert_after_two_failed_runs_once(db, mocks, slack_bot, monkeypatch):
    from bide_followup.config import settings

    monkeypatch.setattr(settings, "admin_alert_slack_channel", "C0ALERTS")
    with db() as s:
        for _ in range(4):
            run.run(s)  # Google isn't connected: every run pauses
        assert s.query(Run).count() == 4
    alerts = [m for m in slack_bot if m["channel"] == "C0ALERTS"]
    assert len(alerts) == 1 and "last two runs failed" in alerts[0]["text"]


def test_gmail_module_never_sends():
    source = inspect.getsource(gmail)
    assert "/send" not in source and "messages" not in source.replace('"message"', "")
