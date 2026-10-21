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
    # Who counts as internal (attendees) and may sign in. Starts from BIDE_DOMAINS.
    "internal_domains": env.bide_domain_list,
    # What Claude is told about the business and which meetings it should treat as sensitive.
    "property_region": "Scotland",
    # The owner's own rules for Claude, in their words: one set for reading notes, one for writing emails.
    "extract_instructions": "",
    "email_instructions": "",
    "sensitive_topics": ["pricing negotiations", "contracts", "staff performance", "legal matters", "HR", "investors"],
    # Pipeline timings: how long a doc must sit unchanged before it is read (FR-3), how far back to look (FR-1),
    # how many failed runs before a meeting is marked failed, how often Gmail drafts are checked, and how long
    # the note text is kept.
    "quiet_minutes": env.quiet_minutes,
    "lookback_days": env.lookback_days,
    "max_attempts": env.max_attempts,
    "gmail_sync_minutes": 30,
    "raw_text_days": env.raw_text_days,
    # Impact page: the minutes a meeting's follow-up took by hand (time saved = meetings × this), and optional
    # before-launch figures Admin can enter, since the app has no data from before it existed.
    "minutes_saved_per_meeting": 20,
    "baseline_followup_rate": None,
    "baseline_followup_days": None,
    # The PRD's success targets (§1), shown against the Impact numbers; and the windows behind two measures.
    "target_minutes_to_drafts": 30,
    "target_unedited_rate": 70,
    "target_reassigned_rate": 5,
    "target_active_days": 4,
    "followup_within_hours": 24,  # "followed up" means within this many hours of the meeting ending
    "routine_stuck_hours": 3,  # Today warns when the Claude Code routine hasn't answered for this long
}


def get(session: Session, key: str) -> Any:
    row = session.scalar(select(Setting).where(Setting.key == key))
    return row.value if row is not None else DEFAULTS[key]


def domains(session: Session) -> list[str]:
    return [d.lower() for d in get(session, "internal_domains")]


def is_internal_email(session: Session, email: str | None) -> bool:
    return bool(email) and email.rsplit("@", 1)[-1].strip().lower() in domains(session)


def in_region(session: Session) -> str:
    """ " in Scotland", or nothing when no region is set: for the prompts' description of the properties."""
    region = get(session, "property_region").strip()
    return f" in {region}" if region else ""


def with_instructions(session: Session, prompt: str, key: str) -> str:
    """The prompt, followed by the owner's instructions from Admin when there are any. The prompt's own rules come
    first and win: an instruction can't make Claude add what the notes don't say."""
    text = get(session, key).strip()
    if not text:
        return prompt
    from bide_followup import catalog  # catalog imports this module

    owner = catalog.owner_name(session)
    return (
        f"{prompt.rstrip()}\n\n## {owner}'s own instructions\n\n"
        f"Follow these too. Where one conflicts with the rules above, the rules above win: never add anything the "
        f"notes don't support.\n\n<instructions>\n{text}\n</instructions>\n"
    )


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
