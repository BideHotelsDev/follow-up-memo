"""The Impact page: whether follow-ups happen, how fast, and whether the team follows through.

Everything is measured from the app's own records, from launch onwards; the app has no data from before it existed,
so a before-launch comparison only appears when Admin enters baseline figures. Definitions are on the page itself.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import catalog, clock, runtime_settings
from bide_followup.catalog import BIDE_WIDE
from bide_followup.integrations import llm
from bide_followup.models import ActionItem, AuditLog, Meeting, Run, User
from bide_followup.schemas.api import (
    ImpactActions,
    ImpactDrafts,
    ImpactHotel,
    ImpactOut,
    ImpactOwner,
    ImpactSystem,
    ImpactSystemWeek,
    ImpactTargets,
    ImpactWeek,
)

ACTED = ("posted", "approved", "closed_in_gmail")


def _local(moment: datetime | None) -> date | None:
    return moment.astimezone(clock.now().tzinfo).date() if moment else None


def _hotels(meeting: Meeting) -> list[str]:
    return list(meeting.properties) or [BIDE_WIDE]


@dataclass
class _Followup:
    meeting: Meeting
    acted_at: datetime | None
    drafts_at: datetime | None
    window: timedelta

    @property
    def end(self) -> datetime:
        return self.meeting.ended_at or self.meeting.started_at or self.meeting.created_at

    @property
    def within_24h(self) -> bool:
        return self.acted_at is not None and self.acted_at - self.end <= self.window


def _followup(meeting: Meeting, window: timedelta) -> _Followup | None:
    """A meeting that needed a follow-up (it produced drafts, or failed and so got none), with when David acted."""
    drafts = [o for o in meeting.outputs if o.type != "run_summary"]
    if not drafts and meeting.status != "failed":
        return None  # nothing to follow up: an internal call with no actions for anyone
    acted = [o.approved_at for o in drafts if o.status in ACTED and o.approved_at]
    return _Followup(meeting, min(acted) if acted else None, min((o.created_at for o in drafts), default=None), window)


def _action_state(item: ActionItem, today: date) -> str | None:
    if item.status == "dismissed":
        return None
    if item.status == "done":
        done = _local(item.done_at)
        return "late" if item.due_date and done and done > item.due_date else "on_time"
    return "overdue" if item.due_date and item.due_date < today else "open"


def _minutes(deltas: list[timedelta]) -> float | None:
    return round(mean(d.total_seconds() for d in deltas) / 60, 1) if deltas else None


def _system(session: Session, meetings: list[Meeting], start: datetime, first_week: date, weeks: int, prop):
    """The work the app did and how reliably: runs, meetings read, drafts written, questions, Claude usage."""
    runs = session.scalars(select(Run).where(Run.started_at >= start)).all()
    failed_runs = [r.started_at for r in runs if r.error]
    skipped = [
        m
        for m in session.scalars(select(Meeting).where(Meeting.started_at >= start, Meeting.status == "skipped"))
        if prop is None or prop in _hotels(m)
    ]
    read = [m for m in meetings if m.status in ("done", "partial")]
    drafts = [o for m in meetings for o in m.outputs if o.type != "run_summary" and o.status != "discarded"]
    slack = [o for o in drafts if o.type in ("slack_dm", "slack_digest")]
    questions = [q for m in meetings for q in m.questions]
    tokens = [m.input_tokens + m.output_tokens for m in read if m.input_tokens or m.output_tokens]

    def week_of(m: Meeting) -> date:
        day = _local(m.started_at)
        return day - timedelta(days=day.weekday())

    series = []
    for i in range(weeks):
        week = first_week + timedelta(weeks=i)
        series.append(
            ImpactSystemWeek(
                week_start=week,
                read=sum(week_of(m) == week for m in read),
                failed=sum(week_of(m) == week and m.status == "failed" for m in meetings),
                skipped=sum(week_of(m) == week for m in skipped),
            )
        )
    return ImpactSystem(
        runs=len(runs),
        runs_ok=len(runs) - len(failed_runs),
        last_failed_run_at=max(failed_runs, default=None),
        meetings_read=len(read),
        meetings_failed=sum(m.status == "failed" for m in meetings),
        meetings_skipped=len(skipped),
        emails_drafted=sum(o.type == "email_draft" for o in drafts),
        slack_drafted=len(slack),
        slack_posted=sum(o.status == "posted" for o in slack),
        questions_asked=len(questions),
        questions_answered=sum(q.answered_at is not None for q in questions),
        tokens_per_meeting=round(mean(tokens)) if tokens else None,
        mode="routine" if llm.routine(session) else "api",
        weeks=series,
    )


def compute(session: Session, weeks: int = 8, prop: str | None = None) -> ImpactOut:
    today = clock.today()
    this_week = today - timedelta(days=today.weekday())
    first_week = this_week - timedelta(weeks=weeks - 1)
    start = datetime.combine(first_week, datetime.min.time(), tzinfo=clock.now().tzinfo)

    meetings = [
        m
        for m in session.scalars(
            select(Meeting).where(Meeting.started_at >= start, Meeting.status.in_(("done", "partial", "failed")))
        )
        if prop is None or prop in _hotels(m)
    ]
    window = timedelta(hours=float(runtime_settings.get(session, "followup_within_hours")))
    followups = [f for m in meetings if (f := _followup(m, window))]

    # Weekly share followed up within 24 hours.
    by_week: dict[date, list[_Followup]] = defaultdict(list)
    for f in followups:
        day = _local(f.meeting.started_at)
        by_week[day - timedelta(days=day.weekday())].append(f)
    series = []
    for i in range(weeks):
        week = first_week + timedelta(weeks=i)
        rows = by_week.get(week, [])
        done = sum(f.within_24h for f in rows)
        series.append(
            ImpactWeek(
                week_start=week,
                meetings=len(rows),
                followed_up=done,
                rate=round(100 * done / len(rows)) if rows else None,
                in_progress=week == this_week,
            )
        )
    within = sum(f.within_24h for f in followups)

    # Actions captured in the period, and who holds the open ones.
    items = [a for m in meetings for a in m.action_items]
    states = {a.id: _action_state(a, today) for a in items}
    counts = defaultdict(int)
    for state in states.values():
        if state:
            counts[state] += 1
    needs = catalog.needs_owner_label(session)
    owners: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in items:
        state = states[a.id]
        if state in ("open", "overdue"):
            name = a.owner.name if a.owner else ("External" if a.owner_name else needs)
            owners[name][0 if state == "open" else 1] += 1

    # Drafts David acted on, and how many he changed first.
    acted = [o for m in meetings for o in m.outputs if o.type != "run_summary" and o.status in ACTED]
    edited_ids = set(
        session.scalars(select(AuditLog.entity_id).where(AuditLog.entity == "output", AuditLog.action == "edit"))
    )
    # Tasks David moved from the owner Claude gave them to someone else: how often Claude got the owner wrong.
    reassigned = 0
    item_ids = {a.id for a in items}
    for log in session.scalars(select(AuditLog).where(AuditLog.entity == "task", AuditLog.action == "update")):
        before, after = log.before or {}, log.after or {}
        if (
            log.entity_id in item_ids
            and before.get("owner_status") == "assigned"
            and before.get("owner_user_id") != after.get("owner_user_id")
        ):
            reassigned += 1
            item_ids.discard(log.entity_id)  # count each task once

    # How often David uses the app: days in the last week with something done by him.
    david = session.scalar(select(User).where(User.role == "owner").order_by(User.created_at))
    active_days = 0
    if david is not None:
        since = clock.utcnow() - timedelta(days=7)
        days = {
            _local(log.created_at)
            for log in session.scalars(
                select(AuditLog).where(AuditLog.user_id == david.id, AuditLog.created_at >= since)
            )
        }
        active_days = len(days)

    hotels = []
    for hotel in [*catalog.property_names(session), BIDE_WIDE] if prop is None else ():
        h_meetings = [m for m in meetings if hotel in _hotels(m)]
        h_follow = [f for f in followups if hotel in _hotels(f.meeting)]
        h_items = [a for m in h_meetings for a in m.action_items]
        h_states = [states[a.id] for a in h_items if states[a.id]]
        done = [s for s in h_states if s in ("on_time", "late")]
        hotels.append(
            ImpactHotel(
                name=hotel,
                meetings=len(h_follow),
                followed_up_rate=round(100 * sum(f.within_24h for f in h_follow) / len(h_follow)) if h_follow else None,
                actions=len(h_states),
                on_time_rate=round(100 * done.count("on_time") / len(done)) if done else None,
                overdue=h_states.count("overdue"),
            )
        )

    processed = [m for m in meetings if m.status in ("done", "partial")]
    done_total = counts["on_time"] + counts["late"]
    return ImpactOut(
        since=first_week,
        weeks=series,
        meetings=len(followups),
        followed_up=within,
        followed_up_rate=round(100 * within / len(followups)) if followups else None,
        minutes_to_drafts=_minutes([f.drafts_at - f.end for f in followups if f.drafts_at]),
        minutes_to_follow_up=_minutes([f.acted_at - f.end for f in followups if f.acted_at]),
        actions=ImpactActions(
            on_time=counts["on_time"],
            late=counts["late"],
            open=counts["open"],
            overdue=counts["overdue"],
            on_time_rate=round(100 * counts["on_time"] / done_total) if done_total else None,
        ),
        owners=[
            ImpactOwner(name=name, open=v[0], overdue=v[1])
            for name, v in sorted(owners.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))
        ],
        drafts=ImpactDrafts(
            acted=len(acted),
            unedited=sum(o.id not in edited_ids for o in acted),
            reassigned=reassigned,
            actions=sum(1 for state in states.values() if state),
        ),
        meetings_handled=len(processed),
        david_active_days=active_days,
        minutes_saved_per_meeting=int(runtime_settings.get(session, "minutes_saved_per_meeting")),
        baseline_followup_rate=runtime_settings.get(session, "baseline_followup_rate"),
        baseline_followup_days=runtime_settings.get(session, "baseline_followup_days"),
        targets=ImpactTargets(**catalog.targets(session)),
        owner_name=catalog.owner_name(session),
        hotels=hotels,
        system=_system(session, meetings, start, first_week, weeks, prop),
    )
