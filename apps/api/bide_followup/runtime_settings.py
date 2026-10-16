"""Settings Admin edits in the app (PRD FR-40), stored in `settings`; defaults here until changed."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup.config import settings as env
from bide_followup.models import Setting

DEFAULTS: dict[str, Any] = {
    "email_tone": "Warm, brief and professional. British English. No exclamation marks.",
    "email_signature": "Best,\nDavid",
    # Slack items always wait for approval in v1 (PRD D4); kept as a setting so the Admin page can show it.
    "slack_mode": "approve",
    "poll_interval_minutes": env.poll_interval_minutes,
}


def get(session: Session, key: str) -> Any:
    row = session.scalar(select(Setting).where(Setting.key == key))
    return row.value if row is not None else DEFAULTS[key]


def all_(session: Session) -> dict[str, Any]:
    stored = {row.key: row.value for row in session.scalars(select(Setting))}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


def put(session: Session, key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.scalar(select(Setting).where(Setting.key == key))
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
