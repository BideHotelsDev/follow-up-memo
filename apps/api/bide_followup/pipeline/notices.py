"""Scheduled Slack messages (PRD v1.1): each person's reminder of tasks due today or overdue, their weekly nudge
about open tasks with no due date, and the owner's weekly digest. The worker calls `send_due` every few minutes; a notice is recorded per person per period, so a repeated call
sends nothing new, and a failed post is retried on the next call until max_attempts.
"""

import logging
from collections import Counter
from datetime import date, datetime, timedelta

from slack_sdk.errors import SlackApiError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import catalog, clock, runtime_settings
from bide_followup.integrations import slack
from bide_followup.models import ActionItem, Meeting, Notice, Output, Question, User
from bide_followup.pipeline.outputs import app_url

log = logging.getLogger(__name__)

WINDOW_HOURS = 4  # a check after this many hours past the set time sends nothing: no 11pm reminders after an outage


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


def _day(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _slack_id(session: Session, user: User) -> str:
    if not user.slack_user_id:
        try:
            user.slack_user_id = slack.user_id_for(session, user.email)
        except (slack.SlackNotConnected, SlackApiError, OSError):
            return ""
    return user.slack_user_id or ""


def _open_tasks(session: Session):
    return select(ActionItem).join(Meeting).where(ActionItem.status == "open", ActionItem.due_date.is_not(None))


def reminder_text(session: Session, user: User, today: date) -> str | None:
    """The reminder for one person, or None when nothing of theirs is due today or overdue."""
    items = session.scalars(
        _open_tasks(session)
        .where(ActionItem.owner_user_id == user.id, ActionItem.due_date <= today)
        .order_by(ActionItem.due_date, ActionItem.created_at)
    ).all()
    if not items:
        return None
    late = [a for a in items if a.due_date < today]
    now = [a for a in items if a.due_date == today]
    lines = [f"*Good morning, {user.name.split()[0]}.* {_plural(len(items), 'task')} from meetings need you:"]
    if late:
        lines.append("\n*Overdue*")
        lines += [f"• {a.description} (due {_day(a.due_date)}, from {a.meeting.title})" for a in late]
    if now:
        lines.append("\n*Due today*")
        lines += [f"• {a.description} (from {a.meeting.title})" for a in now]
    lines.append(f"\n<{app_url('/tasks')}|Open your tasks> to tick them off or change a date.")
    return "\n".join(lines)


NUDGE_LIST = 10


def undated_text(session: Session, user: User, today: date) -> str | None:
    """The weekly nudge for one person: their open tasks with no due date from before today, or None when there are
    none (the daily reminder only covers dated tasks)."""
    start = datetime.combine(today, datetime.min.time(), tzinfo=clock.now().tzinfo)
    items = session.scalars(
        select(ActionItem)
        .join(Meeting)
        .where(
            ActionItem.status == "open",
            ActionItem.due_date.is_(None),
            ActionItem.owner_user_id == user.id,
            ActionItem.created_at < start,
        )
        .order_by(ActionItem.created_at)
    ).all()
    if not items:
        return None
    one = len(items) == 1
    first = user.name.split()[0]
    lines = [f"*{first}, these tasks from meetings have no due date and are still open:*"]
    if one:
        lines = [f"*{first}, this task from a meeting has no due date and is still open:*"]
    lines += [
        f"• {a.description} (from {a.meeting.title}, {_day(a.created_at.astimezone(start.tzinfo).date())})"
        for a in items[:NUDGE_LIST]
    ]
    if len(items) > NUDGE_LIST:
        lines.append(f"• and {len(items) - NUDGE_LIST} more")
    lines.append(f"\n<{app_url('/tasks')}|Open your tasks> to tick off what's done or give the rest a date.")
    return "\n".join(lines)


def digest_text(session: Session, today: date) -> str:
    """The owner's digest of the 7 days before `today`, and what is waiting now."""
    start = today - timedelta(days=7)
    tz = clock.now().tzinfo
    since = datetime.combine(start, datetime.min.time(), tzinfo=tz)
    until = datetime.combine(today, datetime.min.time(), tzinfo=tz)
    owner = catalog.owner_name(session)

    meetings = session.scalars(
        select(Meeting).where(Meeting.started_at >= since, Meeting.started_at < until, Meeting.status != "skipped")
    ).all()
    failed = sum(m.status == "failed" for m in meetings)
    done = session.scalars(select(ActionItem).where(ActionItem.done_at >= since, ActionItem.done_at < until)).all()
    on_time = sum(a.due_date is None or a.done_at.astimezone(tz).date() <= a.due_date for a in done)
    overdue = session.scalars(
        _open_tasks(session).where(ActionItem.due_date < today).order_by(ActionItem.due_date)
    ).all()
    needs = catalog.needs_owner_label(session)

    def who(a: ActionItem) -> str:
        if a.owner is not None:
            return a.owner.name.split()[0]
        return a.owner_name or needs

    open_questions = len(session.scalars(select(Question.id).where(Question.answered_at.is_(None))).all())
    drafts = Counter(
        o.type for o in session.scalars(select(Output).where(Output.status == "draft", Output.type != "run_summary"))
    )
    lines = [f"*{owner}’s week in follow-ups* ({_day(start)} – {_day(today - timedelta(days=1))})"]
    met = f"• {_plural(len(meetings), 'meeting')} processed"
    lines.append(met + (f", {failed} couldn't be" if failed else ""))
    if done:
        lines.append(f"• {_plural(len(done), 'action')} done: {on_time} on time, {len(done) - on_time} late")
    else:
        lines.append("• No actions ticked off")
    if overdue:
        by = Counter(who(a) for a in overdue)
        lines.append(
            f"• {_plural(len(overdue), 'task')} overdue now: " + ", ".join(f"{n} {k}" for k, n in by.most_common())
        )
        lines += [f"    – {a.description} ({who(a)}, due {_day(a.due_date)})" for a in overdue[:5]]
        if len(overdue) > 5:
            lines.append(f"    – and {len(overdue) - 5} more")
    else:
        lines.append("• Nothing overdue")
    waiting = []
    if open_questions:
        waiting.append(_plural(open_questions, "question"))
    if drafts["email_draft"]:
        waiting.append(_plural(drafts["email_draft"], "email draft"))
    if slack_drafts := drafts["slack_dm"] + drafts["slack_digest"]:
        waiting.append(_plural(slack_drafts, "Slack draft"))
    if waiting:
        lines.append("• Waiting for you: " + ", ".join(waiting))
    lines.append(f"\n<{app_url('/')}|Today> · <{app_url('/tasks')}|Tasks> · <{app_url('/impact')}|Impact>")
    return "\n".join(lines)


def _deliver(session: Session, row: Notice) -> None:
    row.attempts += 1
    if not row.recipient:
        row.recipient = _slack_id(session, row.user)
    if not row.recipient:
        row.status, row.error = "failed", f"{row.user.name} has no Slack member ID (Admin → People)"
        return
    try:
        row.external_id = slack.post(session, row.recipient, row.body)
        row.status, row.error = "posted", None
    except (slack.SlackNotConnected, SlackApiError, OSError) as exc:
        row.status, row.error = "failed", str(exc)[:1000]
        log.warning("%s %s failed (%s)", row.kind, row.id, exc.__class__.__name__)


def _send(session: Session, kind: str, user: User, period: date, body: str | None) -> Notice | None:
    row = session.scalar(select(Notice).where(Notice.kind == kind, Notice.user_id == user.id, Notice.period == period))
    if row is not None:
        if row.status == "failed" and row.attempts < runtime_settings.get(session, "max_attempts"):
            _deliver(session, row)
        return row
    if body is None:
        return None
    row = Notice(kind=kind, user_id=user.id, user=user, period=period, body=body, attempts=0, status="failed")
    session.add(row)
    _deliver(session, row)
    return row


def send_reminders(session: Session, today: date) -> list[Notice]:
    people = session.scalars(select(User).where(User.is_active).order_by(User.name)).all()
    sent = [_send(session, "reminder", p, today, reminder_text(session, p, today)) for p in people]
    session.commit()
    return [n for n in sent if n is not None]


def send_undated(session: Session, today: date) -> list[Notice]:
    people = session.scalars(select(User).where(User.is_active).order_by(User.name)).all()
    sent = [_send(session, "undated_nudge", p, today, undated_text(session, p, today)) for p in people]
    session.commit()
    return [n for n in sent if n is not None]


def send_digest(session: Session, today: date) -> Notice | None:
    owner = catalog.owner(session)
    if owner is None:
        return None
    row = _send(session, "weekly_digest", owner, today, digest_text(session, today))
    session.commit()
    return row


def _in_window(now: datetime, hour: int) -> bool:
    return hour <= now.hour < hour + WINDOW_HOURS


def send_due(session: Session, now: datetime | None = None) -> None:
    """Send whatever is due at this moment (UK time): weekday reminders, the weekly undated-task nudge and the weekly
    digest."""
    now = now or clock.now()
    get = lambda key: runtime_settings.get(session, key)
    if get("reminders_enabled") and now.weekday() < 5 and _in_window(now, get("reminder_hour")):
        send_reminders(session, now.date())
    if (
        get("undated_nudge_enabled")
        and now.weekday() == get("undated_nudge_weekday")
        and _in_window(now, get("reminder_hour"))
    ):
        send_undated(session, now.date())
    if get("weekly_digest_enabled") and now.weekday() == get("digest_weekday") and _in_window(now, get("digest_hour")):
        send_digest(session, now.date())
