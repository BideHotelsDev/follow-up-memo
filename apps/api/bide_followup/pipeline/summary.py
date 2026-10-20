"""Stage 6, Summarise (PRD FR-26): one Slack DM to David per run that processed meetings. Together with failure
alerts to Admin, the only messages the app posts without approval.
"""

import logging

from slack_sdk.errors import SlackApiError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import runtime_settings
from bide_followup.config import settings
from bide_followup.integrations import slack
from bide_followup.models import Meeting, Output, Run, User
from bide_followup.pipeline.outputs import app_url, notes_url

log = logging.getLogger(__name__)

STATUS_NOTE = {"partial": "some drafts failed and will retry", "failed": "couldn't be processed"}


def _line(meeting: Meeting) -> str:
    title = f"*<{app_url(f'/meetings/{meeting.id}')}|{meeting.title}>*"
    if meeting.status == "failed":
        return f"• {title}: couldn't be processed. <{notes_url(meeting)}|Notes>"
    parts = []
    actions, questions = len(meeting.action_items), len(meeting.questions)
    parts.append(f"{actions} action{'s' * (actions != 1)}")
    if questions:
        parts.append(f"{questions} question{'s' * (questions != 1)} for you")
    email = next((o for o in meeting.outputs if o.type == "email_draft" and o.status == "draft"), None)
    if email:
        parts.append("Gmail draft ready" + (", review carefully" if email.review_carefully else ""))
    slack_drafts = sum(o.type in ("slack_dm", "slack_digest") and o.status == "draft" for o in meeting.outputs)
    if slack_drafts:
        parts.append(f"{slack_drafts} Slack message{'s' * (slack_drafts != 1)} to approve")
    if meeting.is_sensitive:
        parts.append("sensitive: no team messages")
    if (meeting.extraction or {}).get("notes_quality") in ("thin", "garbled"):
        parts.append("low-quality notes")
    if meeting.status in STATUS_NOTE:
        parts.append(STATUS_NOTE[meeting.status])
    return f"• {title}: {', '.join(parts)}."


def text(meetings: list[Meeting]) -> str:
    n = len(meetings)
    head = f"*{n} meeting{'s' * (n != 1)} followed up.* Nothing has been sent; review in <{app_url('/')}|Follow-up>."
    return "\n".join([head, *(_line(m) for m in meetings)])


def _david(session: Session) -> User | None:
    david = session.scalar(select(User).where(User.role == "owner", User.is_active).order_by(User.created_at))
    if david is not None and not david.slack_user_id:
        try:
            david.slack_user_id = slack.user_id_for(session, david.email)
        except (slack.SlackNotConnected, SlackApiError):
            return david
    return david


def send(session: Session, run: Run, meeting_ids: list) -> Output | None:
    """Post the run summary to David. Recorded as an output so a failed post is visible and retried."""
    if not meeting_ids:
        return None
    meetings = session.scalars(select(Meeting).where(Meeting.id.in_(meeting_ids)).order_by(Meeting.started_at)).all()
    david = _david(session)
    recipient = (david.slack_user_id if david else None) or ""
    row = Output(run_id=run.id, type="run_summary", recipient=recipient, body=text(list(meetings)), attempts=0)
    session.add(row)
    deliver(session, row)
    session.commit()
    return row


def deliver(session: Session, row: Output) -> None:
    row.attempts += 1
    if not row.recipient:
        row.status, row.error = "failed", "The owner has no Slack member ID (Admin → People)"
        return
    try:
        row.external_id = slack.post(session, row.recipient, row.body)
        row.status, row.error = "posted", None
    except (slack.SlackNotConnected, SlackApiError, OSError) as exc:
        row.status, row.error = "failed", str(exc)[:1000]
        log.warning("run summary %s failed (%s)", row.id, exc.__class__.__name__)


def retry_failed(session: Session) -> None:
    rows = session.scalars(
        select(Output).where(
            Output.type == "run_summary",
            Output.status == "failed",
            Output.attempts < runtime_settings.get(session, "max_attempts"),
        )
    ).all()
    for row in rows:
        if not row.recipient and (david := _david(session)) and david.slack_user_id:
            row.recipient = david.slack_user_id
        deliver(session, row)
    session.commit()


def alert_if_failing(session: Session, run: Run) -> None:
    """Alert Admin in Slack when a run fails twice in a row, once per failing streak (PRD §5 Observability)."""
    recent = session.scalars(select(Run).order_by(Run.started_at.desc()).limit(3)).all()
    failing = [r.error is not None for r in recent]
    if failing[:2] != [True, True] or (len(failing) == 3 and failing[2]):
        return
    message = f"Meeting Follow-up: the last two runs failed. Latest: {run.error}\n<{app_url('/admin/runs')}|Run log>"
    if not settings.admin_alert_slack_channel:
        log.error("two runs failed in a row and ADMIN_ALERT_SLACK_CHANNEL is not set: %s", run.error)
        return
    try:
        slack.post(session, settings.admin_alert_slack_channel, message)
    except (slack.SlackNotConnected, SlackApiError, OSError) as exc:
        log.error("couldn't send the admin alert (%s)", exc.__class__.__name__)
