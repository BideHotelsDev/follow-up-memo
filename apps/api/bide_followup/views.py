"""Shared pieces of the review API: who can see what, task buckets, the audit trail, and turning rows into responses.

Roles (PRD §5): David is the owner and reviews everything; Admin (Kyle) can do the same for support; members
(Russell, Sam) see only their own tasks (FR-37). An owner or Admin can view the app as a member (FR-36).
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import clock
from bide_followup.errors import forbidden, not_found
from bide_followup.integrations import gmail
from bide_followup.models import ActionItem, AuditLog, ChannelMap, Meeting, Output, Question, User
from bide_followup.pipeline.outputs import notes_url
from bide_followup.schemas.api import (
    AttendeeOut,
    MeetingOut,
    MeetingRef,
    MeetingSummaryOut,
    OutputOut,
    PersonOut,
    QuestionOut,
    TaskOut,
)

REVIEWERS = ("owner", "admin")


def is_reviewer(user: User) -> bool:
    return user.role in REVIEWERS


def require_reviewer(user: User) -> None:
    if not is_reviewer(user):
        raise forbidden("Only David can review drafts")


def viewer(session: Session, user: User, as_user: uuid.UUID | None) -> User:
    """The person the page is shown for: yourself, or (reviewers only) someone you are viewing as."""
    if as_user is None or as_user == user.id:
        return user
    if not is_reviewer(user):
        raise forbidden("You can only see your own tasks")
    other = session.get(User, as_user)
    if other is None:
        raise not_found("Person")
    return other


def local_day(moment) -> date | None:
    return moment.astimezone(clock.now().tzinfo).date() if moment else None


def bucket(item: ActionItem, today: date) -> str:
    if item.status != "open":
        return "done"
    if item.due_date is None:
        return "nodate"
    if item.due_date < today:
        return "late"
    if item.due_date == today:
        return "today"
    return "week" if item.due_date <= today + timedelta(days=6) else "later"


def audit(session: Session, user: User, entity: str, entity_id: uuid.UUID, action: str, before: Any, after: Any):
    """Record a human change (FR-43)."""
    session.add(
        AuditLog(user_id=user.id, entity=entity, entity_id=entity_id, action=action, before=before, after=after)
    )


def meeting_ref(m: Meeting) -> MeetingRef:
    return MeetingRef(id=m.id, title=m.title, started_at=m.started_at, properties=list(m.properties or []))


def task_out(item: ActionItem, today: date) -> TaskOut:
    return TaskOut(
        id=item.id,
        meeting=meeting_ref(item.meeting),
        description=item.description,
        owner=PersonOut.model_validate(item.owner) if item.owner else None,
        owner_name=item.owner_name,
        owner_status=item.owner_status,
        due_date=item.due_date,
        status=item.status,
        source_quote=item.source_quote,
        bucket=bucket(item, today),
    )


def question_out(q: Question) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        meeting=meeting_ref(q.meeting),
        kind=q.kind,
        text=q.text,
        action_item_id=q.action_item_id,
        answer=q.answer,
        answered_at=q.answered_at,
    )


class Labels:
    """Display names for output recipients: people by Slack ID, channels by ID."""

    def __init__(self, session: Session):
        self.people = {u.slack_user_id: u.name for u in session.scalars(select(User)) if u.slack_user_id}
        self.channels = {
            c.slack_channel_id: f"#{c.slack_channel_name}" if c.slack_channel_name else c.slack_channel_id
            for c in session.scalars(select(ChannelMap))
        }

    def of(self, row: Output) -> str:
        if row.type == "slack_digest":
            return self.channels.get(row.recipient, row.recipient)
        if row.type in ("slack_dm", "run_summary"):
            return self.people.get(row.recipient, row.recipient)
        return row.recipient


def output_out(row: Output, labels: Labels) -> OutputOut:
    return OutputOut(
        id=row.id,
        meeting=meeting_ref(row.meeting) if row.meeting else None,
        type=row.type,
        recipient=row.recipient,
        recipient_label=labels.of(row),
        subject=row.subject,
        body=row.body,
        review_carefully=row.review_carefully,
        status=row.status,
        error=row.error,
        gmail_url=gmail.open_url(row.external_id) if row.type == "email_draft" and row.external_id else None,
        approved_at=row.approved_at,
        updated_at=row.updated_at,
    )


WAITING = ("draft", "failed")


def meeting_summary(m: Meeting) -> MeetingSummaryOut:
    return MeetingSummaryOut(
        id=m.id,
        title=m.title,
        started_at=m.started_at,
        ended_at=m.ended_at,
        properties=list(m.properties or []),
        status=m.status,
        skip_reason=m.skip_reason,
        is_sensitive=m.is_sensitive,
        attendee_count=len(m.attendees),
        action_count=len(m.action_items),
        open_questions=sum(q.answered_at is None for q in m.questions),
        drafts_waiting=sum(o.status in WAITING and o.type != "run_summary" for o in m.outputs),
    )


def meeting_out(session: Session, m: Meeting) -> MeetingOut:
    info = m.extraction or {}
    today = clock.today()
    labels = Labels(session)
    return MeetingOut(
        **meeting_summary(m).model_dump(),
        notes_url=notes_url(m),
        purpose=info.get("meeting", {}).get("purpose"),
        key_points=info.get("key_points", []),
        decisions=info.get("decisions", []),
        open_threads=info.get("open_threads", []),
        systems_mentioned=info.get("systems_mentioned", []),
        notes_quality=info.get("notes_quality"),
        dropped_actions=info.get("dropped_actions", []),
        error=m.error,
        prompt_version=m.prompt_version,
        attendees=[AttendeeOut.model_validate(a) for a in m.attendees],
        tasks=[task_out(a, today) for a in m.action_items],
        questions=[question_out(q) for q in m.questions],
        outputs=[output_out(o, labels) for o in m.outputs if o.status != "discarded"],
    )
