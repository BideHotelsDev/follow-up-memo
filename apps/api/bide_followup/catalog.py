"""What used to be fixed in the code and is now Bide's to edit: the properties, the systems, who the owner is, and the
Impact targets. Everything reads them from here."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import runtime_settings
from bide_followup.models import Property, System, User

BIDE_WIDE = "Bide-wide"  # meetings tagged with no property


def properties(session: Session, active_only: bool = True) -> list[Property]:
    query = select(Property).order_by(Property.sort_order, Property.name)
    if active_only:
        query = query.where(Property.is_active)
    return list(session.scalars(query))


def property_names(session: Session) -> list[str]:
    return [p.name for p in properties(session)]


def system_names(session: Session) -> list[str]:
    return list(session.scalars(select(System.name).where(System.is_active).order_by(System.name)))


def owner(session: Session) -> User | None:
    """The person with the Owner role (David): the one who reviews drafts and gets the run summary."""
    return session.scalar(select(User).where(User.role == "owner", User.is_active).order_by(User.created_at))


def owner_name(session: Session) -> str:
    """The owner's first name, for labels and prompts ("Needs David")."""
    person = owner(session)
    return person.name.split()[0] if person else "the owner"


def needs_owner_label(session: Session) -> str:
    return f"Needs {owner_name(session)}"


TARGET_KEYS = (
    "target_minutes_to_drafts",
    "target_unedited_rate",
    "target_reassigned_rate",
    "target_active_days",
    "followup_within_hours",
    "routine_stuck_hours",
)


def targets(session: Session) -> dict[str, float]:
    return {key: runtime_settings.get(session, key) for key in TARGET_KEYS}
