"""The app's clock. Tests freeze it by patching now()."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from bide_followup.config import settings


def now() -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def today() -> date:
    return now().date()


def utcnow() -> datetime:
    """This moment in UTC, from the same clock as now() (so tests freeze both by patching now)."""
    return now().astimezone(UTC)
