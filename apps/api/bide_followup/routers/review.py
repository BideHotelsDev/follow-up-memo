"""The review API behind the web app (PRD §8): Today, meetings, drafts, tasks and questions."""

import logging
import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from slack_sdk.errors import SlackApiError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bide_followup import clock, impact, runtime_settings, views
from bide_followup.auth import CurrentUser
from bide_followup.db import SessionDep
from bide_followup.errors import DomainError, not_found
from bide_followup.integrations import gmail, google_api, google_oauth, llm, slack
from bide_followup.models import ActionItem, LlmJob, Meeting, Output, Question, Run, User
from bide_followup.pipeline import outputs as pipeline_outputs
from bide_followup.pipeline import run as pipeline
from bide_followup.schemas.api import (
    AnswerIn,
    ApproveAllIn,
    Bucket,
    ImpactOut,
    MeetingOut,
    MeetingStatus,
    MeetingSummaryOut,
    OutputIn,
    OutputOut,
    OutputType,
    PersonOut,
    QuestionOut,
    RunOut,
    TaskIn,
    TaskOut,
    TodayCounts,
    TodayOut,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["review"])

BIDE_WIDE = "Bide-wide"  # the hotel filter's name for meetings tagged with no property


def _property_filter(rows: list[Meeting], prop: str | None) -> list[Meeting]:
    if not prop:
        return rows
    if prop == BIDE_WIDE:
        return [m for m in rows if not m.properties]
    return [m for m in rows if prop in (m.properties or [])]


def _meeting(session: Session, meeting_id: uuid.UUID) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise not_found("Meeting")
    return meeting


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=clock.now().tzinfo)
    return start, start + timedelta(days=1)


# --- people ------------------------------------------------------------------------------------------------------


@router.get("/people")
def people(session: SessionDep, user: CurrentUser) -> list[PersonOut]:
    """Everyone a task can be assigned to (owner pickers, the Viewing as switch)."""
    views.require_reviewer(user)
    rows = session.scalars(select(User).where(User.is_active).order_by(User.name))
    return [PersonOut.model_validate(u) for u in rows]


# --- today -------------------------------------------------------------------------------------------------------


def _tasks_for(session: Session, person: User) -> list[ActionItem]:
    return session.scalars(
        select(ActionItem).where(ActionItem.owner_user_id == person.id, ActionItem.status == "open")
    ).all()


@router.get("/today")
def today(
    session: SessionDep,
    user: CurrentUser,
    as_user: Annotated[uuid.UUID | None, Query(alias="as")] = None,
    property: str | None = None,
) -> TodayOut:
    """The Today page (FR-30): today's meetings, what waits for review, open questions, the viewer's next tasks."""
    person = views.viewer(session, user, as_user)
    day = clock.today()
    reviewer = views.is_reviewer(person)
    start, end = _day_bounds(day)

    def keep(m: Meeting) -> bool:
        return bool(_property_filter([m], property))

    tasks = [t for t in _tasks_for(session, person) if keep(t.meeting)]
    late = [t for t in tasks if views.bucket(t, day) == "late"]
    soon = sorted(
        (t for t in tasks if views.bucket(t, day) in ("late", "today", "week")), key=lambda t: t.due_date or date.max
    )
    meetings: list[Meeting] = []
    questions: list[Question] = []
    problems: list[Meeting] = []
    emails = slack_waiting = 0
    if reviewer:
        meetings = _property_filter(
            session.scalars(
                select(Meeting)
                .where(Meeting.started_at >= start, Meeting.started_at < end)
                .order_by(Meeting.started_at)
            ).all(),
            property,
        )
        questions = [
            q
            for q in session.scalars(
                select(Question).where(Question.answered_at.is_(None)).order_by(Question.created_at)
            )
            if keep(q.meeting)
        ]
        # Failed or partial meetings, and (routine mode) meetings Claude hasn't answered for hours: the routine may
        # have stopped.
        stuck = clock.utcnow() - timedelta(hours=3)
        problems = _property_filter(
            session.scalars(
                select(Meeting)
                .where(
                    or_(
                        Meeting.status.in_(("failed", "partial")),
                        (Meeting.status == "waiting")
                        & Meeting.id.in_(
                            select(LlmJob.meeting_id).where(LlmJob.status == "pending", LlmJob.created_at < stuck)
                        ),
                    )
                )
                .order_by(Meeting.started_at)
            ).all(),
            property,
        )
        waiting = [
            o
            for o in session.scalars(select(Output).where(Output.status == "draft", Output.meeting_id.is_not(None)))
            if keep(o.meeting)
        ]
        emails = sum(o.type == "email_draft" for o in waiting)
        slack_waiting = sum(o.type in ("slack_dm", "slack_digest") for o in waiting)
    last = session.scalar(select(Run).order_by(Run.started_at.desc()).limit(1))
    interval = int(runtime_settings.get(session, "poll_interval_minutes"))
    return TodayOut(
        date=day,
        viewer=PersonOut.model_validate(person),
        counts=TodayCounts(
            questions=len(questions),
            emails=emails,
            slack=slack_waiting,
            tasks_open=len(tasks),
            tasks_overdue=len(late),
        ),
        meetings=[views.meeting_summary(m) for m in meetings],
        questions=[views.question_out(q) for q in questions],
        next_tasks=[views.task_out(t, day) for t in soon[:5]],
        problems=[views.meeting_summary(m) for m in problems],
        last_run=RunOut.model_validate(last) if last else None,
        next_run_at=last.started_at + timedelta(minutes=interval) if last else None,
    )


# --- impact ------------------------------------------------------------------------------------------------------


@router.get("/impact")
def get_impact(
    session: SessionDep,
    user: CurrentUser,
    property: str | None = None,
    weeks: Annotated[int, Query(ge=2, le=26)] = 8,
) -> ImpactOut:
    """The Impact page: follow-up rate and speed, follow-through on actions, draft quality, by week and hotel."""
    views.require_reviewer(user)
    return impact.compute(session, weeks, property)


# --- meetings ----------------------------------------------------------------------------------------------------


@router.get("/meetings")
def list_meetings(
    session: SessionDep,
    user: CurrentUser,
    property: str | None = None,
    status: MeetingStatus | None = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    q: str | None = None,
) -> list[MeetingSummaryOut]:
    """Meetings, newest first, with property, status, date and text filters (FR-31)."""
    views.require_reviewer(user)
    query = select(Meeting).order_by(Meeting.started_at.desc()).limit(300)
    if status:
        query = query.where(Meeting.status == status)
    if from_:
        query = query.where(Meeting.started_at >= _day_bounds(from_)[0])
    if to:
        query = query.where(Meeting.started_at < _day_bounds(to)[1])
    if q:
        query = query.where(Meeting.title.ilike(f"%{q}%"))
    return [views.meeting_summary(m) for m in _property_filter(session.scalars(query).all(), property)]


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> MeetingOut:
    views.require_reviewer(user)
    return views.meeting_out(session, _meeting(session, meeting_id))


@router.post("/meetings/{meeting_id}/reprocess")
def reprocess(meeting_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> MeetingOut:
    """Run extraction again and replace the drafts David hasn't acted on (FR-7). Takes as long as a run does."""
    views.require_reviewer(user)
    meeting = _meeting(session, meeting_id)
    if not llm.enabled():
        raise DomainError("extraction_off", llm.off_reason(), 503)
    before = {"status": meeting.status, "actions": len(meeting.action_items)}
    try:
        token = google_oauth.access_token(session)
        meeting.attempts = 0
        pipeline.process(session, token, meeting)
        session.commit()
        if meeting.status != "skipped":
            pipeline_outputs.generate(session, meeting)
    except llm.Pending as exc:
        # Routine mode: the new request is queued; the routine answers it and the drafts follow.
        meeting.status = "waiting"
        if exc.args and exc.args[0] == "extract":
            meeting.prompt_version = None
        views.audit(session, user, "meeting", meeting.id, "reprocess", before, {"status": "waiting"})
        session.commit()
        return views.meeting_out(session, meeting)
    except google_oauth.GoogleAuthError as exc:
        session.rollback()
        raise DomainError("google_not_connected", str(exc), 503)
    except google_api.GoogleApiError as exc:
        session.rollback()
        raise DomainError("google_error", str(exc), 502)
    except Exception as exc:  # noqa: BLE001 - shown to David; the meeting keeps what it had
        session.rollback()
        log.warning("reprocess %s failed: %s", meeting.id, exc.__class__.__name__)
        raise DomainError("reprocess_failed", f"Couldn't reprocess: {exc.__class__.__name__}", 502)
    views.audit(session, user, "meeting", meeting.id, "reprocess", before, {"status": meeting.status})
    session.commit()
    return views.meeting_out(session, meeting)


# --- drafts ------------------------------------------------------------------------------------------------------


def _output(session: Session, output_id: uuid.UUID) -> Output:
    row = session.get(Output, output_id)
    if row is None or row.meeting_id is None:
        raise not_found("Draft")
    return row


@router.get("/outputs")
def list_outputs(
    session: SessionDep,
    user: CurrentUser,
    type: OutputType | None = None,
    status: str | None = Query(default=None, description="Comma-separated statuses"),
    property: str | None = None,
) -> list[OutputOut]:
    """Email and Slack drafts (FR-32, FR-33), newest meeting first. Run summaries are not drafts and aren't listed."""
    views.require_reviewer(user)
    query = select(Output).join(Meeting).where(Output.type != "run_summary").order_by(Meeting.started_at.desc())
    if type:
        query = query.where(Output.type == type)
    if status:
        query = query.where(Output.status.in_(status.split(",")))
    else:
        query = query.where(Output.status != "discarded")
    rows = session.scalars(query.limit(500)).all()
    labels = views.Labels(session)
    keep = {m.id for m in _property_filter([r.meeting for r in rows], property)}
    return [views.output_out(r, labels) for r in rows if r.meeting_id in keep]


@router.patch("/outputs/{output_id}")
def edit_output(output_id: uuid.UUID, body: OutputIn, session: SessionDep, user: CurrentUser) -> OutputOut:
    """Edit a draft's text. An email edit updates the Gmail draft too."""
    views.require_reviewer(user)
    row = _output(session, output_id)
    if row.status not in ("draft", "failed"):
        raise DomainError("not_a_draft", "Only drafts can be edited")
    before = {"subject": row.subject, "body": row.body}
    if body.subject is not None and row.type == "email_draft":
        row.subject = body.subject
    if body.body is not None:
        row.body = body.body
    if row.type == "email_draft":
        pipeline_outputs.deliver_email(session, row)
        if row.status == "failed":
            session.rollback()
            raise DomainError("gmail_error", "Gmail didn't take the change; try again", 502)
    views.audit(session, user, "output", row.id, "edit", before, {"subject": row.subject, "body": row.body})
    session.commit()
    return views.output_out(row, views.Labels(session))


def _approve(session: Session, user: User, row: Output) -> None:
    """Post an approved Slack draft as the bot. Nothing else ever posts a team message."""
    if row.type not in ("slack_dm", "slack_digest"):
        raise DomainError("not_slack", "Emails are sent from Gmail; open the draft there")
    if row.status != "draft":
        raise DomainError("not_a_draft", "This draft was already handled")
    try:
        row.external_id = slack.post(session, row.recipient, row.body)
    except slack.SlackNotConnected as exc:
        raise DomainError("slack_not_connected", str(exc), 503)
    except SlackApiError as exc:
        error = exc.response.get("error", "error")
        # An archived channel or a removed bot fails this one draft; the others go on (PRD §9).
        row.status, row.error = "failed", f"Slack: {error}"
        session.commit()
        raise DomainError("slack_error", f"Slack refused the message ({error})", 502)
    row.status, row.error = "posted", None
    row.approved_by_id, row.approved_at = user.id, clock.utcnow()
    views.audit(session, user, "output", row.id, "approve", {"status": "draft"}, {"status": "posted"})


@router.post("/outputs/{output_id}/approve")
def approve(output_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> OutputOut:
    views.require_reviewer(user)
    row = _output(session, output_id)
    _approve(session, user, row)
    session.commit()
    return views.output_out(row, views.Labels(session))


@router.post("/outputs/approve-all")
def approve_all(body: ApproveAllIn, session: SessionDep, user: CurrentUser) -> list[OutputOut]:
    """Approve every waiting Slack draft, of one meeting or of all. Stops at the first Slack refusal."""
    views.require_reviewer(user)
    query = select(Output).where(Output.type.in_(("slack_dm", "slack_digest")), Output.status == "draft")
    if body.meeting_id:
        query = query.where(Output.meeting_id == body.meeting_id)
    rows = session.scalars(query).all()
    for row in rows:
        _approve(session, user, row)
        session.commit()
    labels = views.Labels(session)
    return [views.output_out(r, labels) for r in rows]


@router.post("/outputs/{output_id}/discard")
def discard(output_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> OutputOut:
    """Discard a draft. An email's Gmail draft is deleted too."""
    views.require_reviewer(user)
    row = _output(session, output_id)
    if row.status not in ("draft", "failed"):
        raise DomainError("not_a_draft", "This draft was already handled")
    if row.type == "email_draft" and row.external_id:
        try:
            gmail.delete_draft(google_oauth.access_token(session), row.external_id)
        except (gmail.GmailError, google_oauth.GoogleAuthError) as exc:
            raise DomainError("gmail_error", f"Couldn't delete the Gmail draft: {exc}", 502)
    before = row.status
    row.status = "discarded"
    views.audit(session, user, "output", row.id, "discard", {"status": before}, {"status": "discarded"})
    session.commit()
    return views.output_out(row, views.Labels(session))


# --- tasks -------------------------------------------------------------------------------------------------------


def _task(session: Session, user: User, task_id: uuid.UUID) -> ActionItem:
    item = session.get(ActionItem, task_id)
    if item is None or (not views.is_reviewer(user) and item.owner_user_id != user.id):
        raise not_found("Task")
    return item


@router.get("/tasks")
def list_tasks(
    session: SessionDep,
    user: CurrentUser,
    owner: str | None = Query(default=None, description="A person's id, 'needs_david' or 'external'"),
    bucket: Bucket | None = None,
    property: str | None = None,
    q: str | None = None,
    as_user: Annotated[uuid.UUID | None, Query(alias="as")] = None,
) -> list[TaskOut]:
    """Every action from every meeting (FR-34). Members, and anyone viewed as a member, get only their own."""
    person = views.viewer(session, user, as_user)
    query = select(ActionItem).join(Meeting).order_by(ActionItem.due_date.is_(None), ActionItem.due_date)
    if not views.is_reviewer(person):
        query = query.where(ActionItem.owner_user_id == person.id)
    elif owner == "needs_david":
        query = query.where(ActionItem.owner_status == "needs_david")
    elif owner == "external":
        query = query.where(ActionItem.owner_user_id.is_(None), ActionItem.owner_name.is_not(None))
    elif owner:
        query = query.where(ActionItem.owner_user_id == uuid.UUID(owner))
    if q:
        query = query.where(or_(ActionItem.description.ilike(f"%{q}%"), Meeting.title.ilike(f"%{q}%")))
    day = clock.today()
    rows = session.scalars(query.limit(1000)).all()
    keep = {m.id for m in _property_filter([r.meeting for r in rows], property)}
    out = [views.task_out(r, day) for r in rows if r.meeting_id in keep]
    return [t for t in out if bucket is None or t.bucket == bucket]


def _set_owner(session: Session, item: ActionItem, owner_id: uuid.UUID | None) -> None:
    if owner_id is None:
        item.owner_user_id, item.owner_name, item.owner_status = None, None, "needs_david"
        return
    person = session.get(User, owner_id)
    if person is None or not person.is_active:
        raise not_found("Person")
    item.owner_user_id, item.owner_name, item.owner_status = person.id, None, "assigned"


def _snapshot(item: ActionItem) -> dict:
    return {
        "owner_user_id": str(item.owner_user_id) if item.owner_user_id else None,
        "owner_status": item.owner_status,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "status": item.status,
    }


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskIn, session: SessionDep, user: CurrentUser) -> TaskOut:
    """Change a task's owner, due date or status. Members can only mark their own tasks done or open again."""
    item = _task(session, user, task_id)
    sent = body.model_fields_set
    if not views.is_reviewer(user) and sent - {"status"}:
        raise DomainError("forbidden", "Only David can reassign or reschedule tasks", 403)
    before = _snapshot(item)
    if "owner_user_id" in sent:
        _set_owner(session, item, body.owner_user_id)
    if "due_date" in sent:
        item.due_date = body.due_date
    if "status" in sent and body.status and body.status != item.status:
        item.status = body.status
        item.done_at = clock.utcnow() if body.status == "done" else None
    session.flush()
    if sent & {"owner_user_id", "due_date"}:
        pipeline_outputs.refresh_slack(session, item.meeting)
    views.audit(session, user, "task", item.id, "update", before, _snapshot(item))
    session.commit()
    return views.task_out(item, clock.today())


# --- questions ---------------------------------------------------------------------------------------------------


@router.post("/questions/{question_id}/answer")
def answer(question_id: uuid.UUID, body: AnswerIn, session: SessionDep, user: CurrentUser) -> QuestionOut:
    """Answer a question for David. An owner or due question updates its action, and the meeting's Slack drafts are
    rebuilt to match (FR-35)."""
    views.require_reviewer(user)
    question = session.get(Question, question_id)
    if question is None:
        raise not_found("Question")
    item = session.get(ActionItem, question.action_item_id) if question.action_item_id else None
    if question.kind == "owner" and item is not None:
        if "owner_user_id" not in body.model_fields_set:
            raise DomainError("answer_required", "Pick who owns this", 422)
        _set_owner(session, item, body.owner_user_id)
        question.answer = item.owner.name if item.owner else "Needs David"
    elif question.kind == "due" and item is not None:
        item.due_date = body.due_date
        question.answer = body.due_date.isoformat() if body.due_date else "No date"
    else:
        if not (body.text and body.text.strip()):
            raise DomainError("answer_required", "Type an answer", 422)
        question.answer = body.text.strip()
    question.answered_at = clock.utcnow()
    session.flush()
    if item is not None:
        pipeline_outputs.refresh_slack(session, question.meeting)
    views.audit(session, user, "question", question.id, "answer", None, {"answer": question.answer})
    session.commit()
    return views.question_out(question)


@router.post("/questions/{question_id}/reopen")
def reopen(question_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> QuestionOut:
    """Undo an answer (the action keeps the value it was given; change it on the task)."""
    views.require_reviewer(user)
    question = session.get(Question, question_id)
    if question is None:
        raise not_found("Question")
    before = {"answer": question.answer}
    question.answer, question.answered_at = None, None
    views.audit(session, user, "question", question.id, "answer", before, None)
    session.commit()
    return views.question_out(question)
