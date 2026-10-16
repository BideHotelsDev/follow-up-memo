"""Seed data. `python -m bide_followup.seed` makes the owner and Admin (safe to re-run). `--demo` adds Russell and
Sam with sample addresses, a channel map and skip rules for a local demo; `--mock` also connects a pretend Google
account for the mock services. Never run --demo or --mock against production."""

import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bide_followup.db import SessionLocal
from bide_followup.integrations import google_oauth
from bide_followup.models import ChannelMap, SkipRule, User

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
        token = {"access_token": "mock", "refresh_token": "mock-refresh", "expires_in": 0}
        google_oauth.save(session, "david@liddellpropertyinvestments.com", token)


if __name__ == "__main__":
    with SessionLocal() as s:
        base(s)
        if "--demo" in sys.argv:
            demo(s)
        if "--mock" in sys.argv:
            mock_google(s)
    print("seeded")
