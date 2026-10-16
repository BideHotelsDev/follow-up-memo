"""Stages 4 and 5, Generate and Deliver drafts (PRD §6): build each output from the validated extraction and upsert it
into `outputs` by its unique key; create or update the Gmail draft. Slack items stay in the app until David approves
them (routers, Phase 4). Each output is built and delivered on its own: one failure never blocks the others.

The email is written by Claude from the validated JSON only (never the notes); Slack messages are fixed templates.
"""

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import clock, runtime_settings
from bide_followup.config import settings
from bide_followup.integrations import gmail, google_oauth, llm
from bide_followup.models import ChannelMap, Meeting, Output, Question, User
from bide_followup.pipeline.extract import PROMPTS
from bide_followup.schemas.extraction import MAX_QUESTIONS

log = logging.getLogger(__name__)

EMAIL_PROMPT = "email_v1"
EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}
# Outputs a person has acted on are never rewritten by the pipeline.
SETTLED = ("approved", "posted", "discarded", "closed_in_gmail")


def notes_url(meeting: Meeting) -> str:
    return f"https://docs.google.com/document/d/{meeting.drive_file_id}/edit"


def app_url(path: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}{path}"


def _day(meeting: Meeting) -> date:
    return (meeting.started_at or clock.utcnow()).astimezone(clock.now().tzinfo).date()


def _due(day: date | None) -> str:
    return f"due {day:%a %-d %b}" if day else "no date set"


def _owner_label(item) -> str:
    if item.owner is not None:
        return item.owner.name
    return item.owner_name or "Needs David"


# --- building ---------------------------------------------------------------------------------------------------


def email_draft(session: Session, meeting: Meeting) -> dict | None:
    """The follow-up email to external attendees, or None when there is nobody external to write to (FR-21)."""
    recipients = sorted({a.email for a in meeting.attendees if not a.is_internal and a.email})
    if not recipients:
        return None
    info = meeting.extraction or {}
    names = [a.name for a in meeting.attendees if not a.is_internal and a.email]
    payload = {
        "meeting": {"title": meeting.title, "date": _day(meeting).isoformat(), **info.get("meeting", {})},
        "recipients": names,
        "key_points": info.get("key_points", []),
        "decisions": info.get("decisions", []),
        "next_steps": [
            {"action": a.description, "owner": _owner_label(a), "due": a.due_date and a.due_date.isoformat()}
            for a in meeting.action_items
        ],
    }
    system = (
        (PROMPTS / f"{EMAIL_PROMPT}.md")
        .read_text()
        .format(
            tone=runtime_settings.get(session, "email_tone"), signature=runtime_settings.get(session, "email_signature")
        )
    )
    messages = [{"role": "user", "content": json.dumps(payload, indent=2)}]
    completion = llm.complete(system, messages, EMAIL_SCHEMA, session=session, kind="email", meeting_id=meeting.id)
    meeting.input_tokens += completion.input_tokens
    meeting.output_tokens += completion.output_tokens
    written = json.loads(completion.text)
    return {
        "type": "email_draft",
        "recipient": ", ".join(recipients),
        "subject": written["subject"].strip(),
        "body": written["body"].strip(),
        # Sensitive meetings still get an email, flagged for a careful read (FR-27).
        "review_carefully": meeting.is_sensitive,
    }


def slack_dms(meeting: Meeting, david: User | None) -> list[dict]:
    """One DM per internal owner other than David, listing their actions (FR-22). None for sensitive meetings."""
    if meeting.is_sensitive:
        return []
    by_owner: dict[str, tuple[User, list]] = {}
    for item in meeting.action_items:
        owner = item.owner
        if owner is None or (david and owner.id == david.id) or not owner.slack_user_id:
            continue
        by_owner.setdefault(owner.slack_user_id, (owner, []))[1].append(item)
    dms = []
    for slack_id, (owner, items) in sorted(by_owner.items()):
        purpose = (meeting.extraction or {}).get("meeting", {}).get("purpose", "")
        lines = [
            f"Hi {owner.name.split()[0]}, your actions from *{meeting.title}* ({_day(meeting):%a %-d %b}):",
            *(f"• {i.description} ({_due(i.due_date)})" for i in items),
        ]
        if purpose:
            lines.append(f"\n_{purpose}_")
        lines.append(f"<{notes_url(meeting)}|Meeting notes>")
        dms.append({"type": "slack_dm", "recipient": slack_id, "body": "\n".join(lines)})
    return dms


def digest_channel(session: Session, meeting: Meeting) -> ChannelMap | None:
    """The channel for a meeting's digest: a mapped topic named in its title or purpose, else its first property."""
    rows = session.scalars(select(ChannelMap)).all()
    text = f"{meeting.title} {(meeting.extraction or {}).get('meeting', {}).get('purpose', '')}".lower()
    for row in rows:
        if row.topic and row.topic.lower() in text:
            return row
    for prop in meeting.properties:
        for row in rows:
            if row.property == prop:
                return row
    return None


def slack_digest(session: Session, meeting: Meeting) -> dict | None:
    """The channel digest (FR-23). None for sensitive meetings or when no channel is mapped."""
    if meeting.is_sensitive:
        return None
    channel = digest_channel(session, meeting)
    if channel is None:
        return None
    info = meeting.extraction or {}
    lines = [f"*{meeting.title}* ({_day(meeting):%a %-d %b})"]
    if purpose := info.get("meeting", {}).get("purpose"):
        lines.append(purpose)
    if info.get("decisions"):
        lines += ["", "*Decisions*", *(f"• {d}" for d in info["decisions"])]
    if meeting.action_items:
        lines += [
            "",
            "*Actions*",
            *(f"• {a.description} — {_owner_label(a)}, {_due(a.due_date)}" for a in meeting.action_items),
        ]
    lines.append(f"\n<{notes_url(meeting)}|Meeting notes>")
    return {"type": "slack_digest", "recipient": channel.slack_channel_id, "body": "\n".join(lines)}


def _missing_email_questions(meeting: Meeting) -> None:
    """External attendees with no email can't get the follow-up: ask David (PRD §9 Edge cases)."""
    asked = {q.text for q in meeting.questions}
    for a in meeting.attendees:
        if a.is_internal or a.email or len(meeting.questions) >= MAX_QUESTIONS:
            continue
        text = f"What is {a.name}'s email address? They aren't on the follow-up email."
        if text not in asked:
            meeting.questions.append(Question(text=text))


# --- storing and delivering --------------------------------------------------------------------------------------


def upsert(session: Session, meeting: Meeting, spec: dict) -> Output | None:
    """Insert or update by (meeting, type, recipient). An output someone has acted on is left alone."""
    row = session.scalar(
        select(Output).where(
            Output.meeting_id == meeting.id, Output.type == spec["type"], Output.recipient == spec["recipient"]
        )
    )
    if row is not None and row.status in SETTLED:
        return None
    if row is None:
        row = Output(type=spec["type"], recipient=spec["recipient"], body="", attempts=0)
        meeting.outputs.append(row)
    row.subject = spec.get("subject")
    row.body = spec["body"]
    row.review_carefully = spec.get("review_carefully", False)
    row.status, row.error = "draft", None
    return row


def deliver_email(session: Session, row: Output) -> None:
    """Create or update the Gmail draft. Failure marks the output failed; the next run retries it."""
    row.attempts += 1
    try:
        token = google_oauth.access_token(session)
        to = [e.strip() for e in row.recipient.split(",")]
        subject = row.subject or ""
        if row.external_id:
            try:
                row.external_id = gmail.update_draft(token, row.external_id, to, subject, row.body)
            except gmail.GmailError as exc:
                if exc.status != 404:
                    raise
                row.external_id = gmail.create_draft(token, to, subject, row.body)  # David deleted it; start over
        else:
            row.external_id = gmail.create_draft(token, to, subject, row.body)
        row.status, row.error = "draft", None
    except (gmail.GmailError, google_oauth.GoogleAuthError, OSError) as exc:
        row.status, row.error = "failed", str(exc)[:1000]
        log.warning("output %s: Gmail draft failed (%s)", row.id, exc.__class__.__name__)


def _failed(session: Session, meeting: Meeting, type_: str, recipient: str, exc: Exception) -> None:
    row = upsert(session, meeting, {"type": type_, "recipient": recipient, "body": ""})
    if row is not None:
        row.status, row.error = "failed", f"{exc.__class__.__name__}: {exc}"[:1000]
        row.attempts += 1


def _david(session: Session) -> User | None:
    return session.scalar(select(User).where(User.role == "owner", User.is_active).order_by(User.created_at))


def _store(session: Session, meeting: Meeting, specs: list[dict], types: tuple[str, ...], keep: set) -> None:
    """Upsert the specs and remove drafts of these types that are no longer wanted (a recipient gone after a
    reprocess, an owner changed by David); deliver email drafts to Gmail."""
    keep = keep | {(s["type"], s["recipient"]) for s in specs}
    for row in list(meeting.outputs):
        if row.type in types and row.status == "draft" and (row.type, row.recipient) not in keep:
            remove_draft(session, row)
    for spec in specs:
        row = upsert(session, meeting, spec)
        if row is not None and row.type == "email_draft":
            session.flush()
            deliver_email(session, row)
    session.flush()


def refresh_slack(session: Session, meeting: Meeting) -> None:
    """Rebuild a meeting's Slack drafts after its actions change (an answered question, a task edit). Drafts David
    already approved or discarded are left alone."""
    specs = slack_dms(meeting, _david(session))
    if digest := slack_digest(session, meeting):
        specs.append(digest)
    _store(session, meeting, specs, ("slack_dm", "slack_digest"), set())


def generate(session: Session, meeting: Meeting) -> None:
    """Build and store every output for a meeting, then set its status: done, or partial if any output failed."""
    _missing_email_questions(meeting)
    specs: list[dict] = []
    keep: set = set()
    email_waiting = False
    try:
        if email := email_draft(session, meeting):
            specs.append(email)
    except llm.Pending:
        email_waiting = True  # with the Claude Code routine; keep any earlier draft until the new one arrives
        recipients = ", ".join(sorted({a.email for a in meeting.attendees if not a.is_internal and a.email}))
        keep.add(("email_draft", recipients))
    except Exception as exc:  # noqa: BLE001 - Claude unreachable, declined or malformed: the email retries, the rest go on
        log.warning("meeting %s: email draft failed (%s)", meeting.id, exc.__class__.__name__)
        recipients = ", ".join(sorted({a.email for a in meeting.attendees if not a.is_internal and a.email}))
        previous = next((o for o in meeting.outputs if o.type == "email_draft" and o.recipient == recipients), None)
        if previous is not None and previous.status == "draft" and previous.body:
            keep.add(("email_draft", recipients))  # a rewrite failed: keep the draft David already has
        else:
            _failed(session, meeting, "email_draft", recipients, exc)
            keep.add(("email_draft", recipients))
    specs += slack_dms(meeting, _david(session))
    if digest := slack_digest(session, meeting):
        specs.append(digest)
    _store(session, meeting, specs, ("email_draft", "slack_dm", "slack_digest"), keep)
    if email_waiting:
        meeting.status = "waiting"
    else:
        meeting.status = "partial" if any(o.status == "failed" for o in meeting.outputs) else "done"


def remove_draft(session: Session, row: Output) -> None:
    """Delete an unapproved output, and its Gmail draft."""
    if row.type == "email_draft" and row.external_id:
        try:
            gmail.delete_draft(google_oauth.access_token(session), row.external_id)
        except (gmail.GmailError, google_oauth.GoogleAuthError, OSError):
            log.warning("output %s: couldn't delete the Gmail draft", row.id)
    row.meeting.outputs.remove(row)


def retry_failed(session: Session) -> int:
    """Retry outputs that failed on an earlier run, up to the attempt limit (PRD §5 Reliability)."""
    rows = session.scalars(
        select(Output).where(
            Output.status == "failed", Output.meeting_id.is_not(None), Output.attempts < settings.max_attempts
        )
    ).all()
    for row in rows:
        meeting = row.meeting
        if row.type == "email_draft":
            if row.body:
                deliver_email(session, row)
            else:  # the email itself was never written: generate the meeting's outputs again
                generate(session, meeting)
                continue
        meeting.status = "partial" if any(o.status == "failed" for o in meeting.outputs) else "done"
    session.commit()
    return len(rows)


def sync_gmail(session: Session) -> int:
    """Mark email drafts David has sent or deleted in Gmail (PRD §9 Edge cases). Returns the drafts closed."""
    rows = session.scalars(
        select(Output).where(Output.type == "email_draft", Output.status == "draft", Output.external_id.is_not(None))
    ).all()
    if not rows:
        return 0
    token = google_oauth.access_token(session)
    closed = 0
    for row in rows:
        if not gmail.draft_exists(token, row.external_id):
            row.status, row.approved_at = "closed_in_gmail", clock.utcnow()
            closed += 1
    session.commit()
    return closed
