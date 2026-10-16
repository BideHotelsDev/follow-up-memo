"""Seed data. `python -m bide_followup.seed` makes the owner and Admin (safe to re-run). `--demo` adds Russell and
Sam with sample addresses, a channel map and skip rules for a local demo; `--mock` also connects a pretend Google
account and Slack bot for the mock services, and eight weeks of made-up history for the Impact page. Never run
--demo or --mock against production."""

import random
import sys
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bide_followup import clock
from bide_followup.db import SessionLocal
from bide_followup.integrations import google_oauth, slack
from bide_followup.models import ActionItem, ChannelMap, Meeting, Output, SkipRule, User

PEOPLE = [
    {"email": "david@liddellpropertyinvestments.com", "name": "David", "role": "owner", "ownership_areas": []},
    {"email": "kyle@bidehotels.com", "name": "Kyle", "role": "admin", "ownership_areas": []},
]
DEMO_PEOPLE = [
    {
        "email": "russell@bidehotels.com",
        "name": "Russell",
        "role": "member",
        "ownership_areas": ["operations", "Operto", "housekeeping"],
    },
    {
        "email": "sam@bidehotels.com",
        "name": "Sam",
        "role": "member",
        "ownership_areas": ["revenue", "PriceLabs", "OTAs", "Canary"],
    },
]
DEMO_CHANNELS = [
    {"topic": "revenue", "slack_channel_id": "C0REVENUE", "slack_channel_name": "revenue"},
    {"topic": "operations", "slack_channel_id": "C0OPS", "slack_channel_name": "operations"},
    {"property": "The View", "slack_channel_id": "C0VIEW", "slack_channel_name": "the-view"},
    {"property": "The Hearth", "slack_channel_id": "C0HEARTH", "slack_channel_name": "the-hearth"},
    {"property": "The Villa", "slack_channel_id": "C0VILLA", "slack_channel_name": "the-villa"},
]
DEMO_SKIP_RULES = [("title_keyword", "1:1"), ("title_keyword", "interview")]


def _people(session: Session, specs: list[dict]) -> None:
    for spec in specs:
        if session.scalar(select(User).where(func.lower(User.email) == spec["email"])) is None:
            session.add(User(**spec))


def base(session: Session) -> None:
    _people(session, PEOPLE)
    session.commit()


def demo(session: Session) -> None:
    _people(session, DEMO_PEOPLE)
    if session.scalar(select(func.count()).select_from(ChannelMap)) == 0:
        session.add_all(ChannelMap(**spec) for spec in DEMO_CHANNELS)
    if session.scalar(select(func.count()).select_from(SkipRule)) == 0:
        session.add_all(SkipRule(type=t, value=v) for t, v in DEMO_SKIP_RULES)
    session.commit()


def mock_google(session: Session) -> None:
    if google_oauth.integration(session) is None:
        # Never expires, so it is never refreshed: sign-in can use the real Google while the APIs are mocked.
        token = {"access_token": "mock", "refresh_token": "mock-refresh", "expires_in": 10 * 365 * 24 * 3600}
        google_oauth.save(session, "david@liddellpropertyinvestments.com", token)
    if slack.integration(session) is None:
        slack.save(
            session, {"access_token": "xoxb-mock", "scope": ",".join(slack.BOT_SCOPES), "team": {"name": "Mock"}}
        )


HISTORY = [
    ("Weekly revenue", ["The View", "The Hearth"]),
    ("Housekeeping sync", ["The Villa"]),
    ("Owners call", ["The Villa"]),
    ("Opening snag list", ["The View"]),
    ("Linen supply review", ["The View"]),
    ("Morning huddle", []),
    ("Website review", []),
    ("Photography brief", ["The Hearth"]),
]
TASKS = [
    "Send the rate sheet",
    "Chase the boiler engineer",
    "Book the final clean",
    "Update the Canary message",
    "Confirm floor rates in PriceLabs",
    "Order welcome packs",
    "Send revised linen volumes",
]


def mock_history(session: Session, weeks: int = 8) -> None:
    """Made-up past meetings so the Impact page has something to show. Mock databases only: never production."""
    if session.scalar(select(func.count()).select_from(Meeting).where(Meeting.drive_file_id.like("history-%"))):
        return
    rng = random.Random(7)
    people = [u for u in session.scalars(select(User).where(User.role != "admin"))]
    today = clock.today()
    for back in range(weeks * 7, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        weeks_in = weeks - back // 7  # later weeks follow up more, as the habit forms
        for n in range(rng.randint(1, 3)):
            title, props = rng.choice(HISTORY)
            start = datetime.combine(day, time(9 + 2 * n, 0), tzinfo=clock.now().tzinfo)
            m = Meeting(
                drive_file_id=f"history-{day}-{n}",
                title=title,
                started_at=start,
                ended_at=start + timedelta(minutes=40),
                properties=props,
                status="done" if rng.random() > 0.04 else "failed",
                extraction={"notes_quality": "good"},
            )
            session.add(m)
            if m.status == "failed":
                continue
            acted = rng.random() < 0.45 + 0.06 * weeks_in
            delay = timedelta(hours=rng.choice([1, 2, 3, 5, 8, 20, 30]))
            for kind in ("email_draft", "slack_dm"):
                if kind == "email_draft" and rng.random() < 0.4:
                    continue
                o = Output(
                    type=kind,
                    recipient=f"{m.drive_file_id}-{kind}",
                    body="(made-up history)",
                    attempts=1,
                    status=("closed_in_gmail" if kind == "email_draft" else "posted") if acted else "draft",
                )
                o.created_at = m.ended_at + timedelta(minutes=rng.randint(12, 28))
                o.approved_at = m.ended_at + delay if acted else None
                m.outputs.append(o)
            for _ in range(rng.randint(1, 3)):
                owner = rng.choice(people)
                due = day + timedelta(days=rng.randint(1, 10)) if rng.random() < 0.7 else None
                done = rng.random() < 0.75 and (due is None or due < today or rng.random() < 0.4)
                done_on = (due or day) + timedelta(days=rng.choice([-2, -1, 0, 0, 1, 3])) if done else None
                m.action_items.append(
                    ActionItem(
                        description=rng.choice(TASKS),
                        owner_user_id=owner.id,
                        owner_status="assigned",
                        due_date=due,
                        status="done" if done else "open",
                        done_at=datetime.combine(min(done_on, today), time(15), tzinfo=clock.now().tzinfo)
                        if done_on
                        else None,
                    )
                )
    session.commit()


if __name__ == "__main__":
    with SessionLocal() as s:
        base(s)
        if "--demo" in sys.argv:
            demo(s)
        if "--mock" in sys.argv:
            mock_google(s)
            mock_history(s)
    print("seeded")
