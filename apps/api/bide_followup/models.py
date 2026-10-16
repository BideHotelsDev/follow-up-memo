"""The app's tables (PRD §7 Data model). Every table has a UUID id, created_at and updated_at."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bide_followup import clock

JsonType = JSON().with_variant(JSONB(), "postgresql")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    # The app's clock, so stored timestamps agree with everything else that reads the time (and tests can freeze it).
    return clock.utcnow()


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class UtcDateTime(TypeDecorator):
    """A moment in UTC that reads back timezone-aware on every database (SQLite drops the zone; Postgres keeps it)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Timestamped:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Set in Python rather than by the database, so SQLite and Postgres store comparable values.
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


ROLES = ("admin", "owner", "member")


class User(Timestamped, Base):
    """David = owner; Russell, Sam = member; Kyle = admin. Sign-in is invite-only: a person must have a row here."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="member")
    slack_user_id: Mapped[str | None] = mapped_column(String(32))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Topics this person owns by default (e.g. "housekeeping", "pricing"); the extraction prompt carries them.
    ownership_areas: Mapped[list[str]] = mapped_column(JsonType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(UtcDateTime())


PROVIDERS = ("google", "slack")
INTEGRATION_STATUSES = ("connected", "error", "revoked")


class Integration(Timestamped, Base):
    """One row per connected account. Tokens are Fernet-encrypted (crypto.py) and never logged."""

    __tablename__ = "integrations"
    __table_args__ = (
        CheckConstraint(_in("provider", PROVIDERS), name="provider"),
        CheckConstraint(_in("status", INTEGRATION_STATUSES), name="status"),
    )

    provider: Mapped[str] = mapped_column(String(16), unique=True)
    account_email: Mapped[str | None] = mapped_column(String(254))
    # Slack: the workspace (team) ID; Google: unused.
    external_id: Mapped[str | None] = mapped_column(String(64))
    encrypted_tokens: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(JsonType, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    status: Mapped[str] = mapped_column(String(16), default="connected")
    last_error: Mapped[str | None] = mapped_column(Text)


class Setting(Timestamped, Base):
    """Admin-editable settings: email tone, signature, slack_mode, polling interval, Bide domain."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[Any] = mapped_column(JsonType)


class ChannelMap(Timestamped, Base):
    """Where a meeting's digest goes: by topic (revenue → #revenue) or property (The View → #the-view)."""

    __tablename__ = "channel_map"
    __table_args__ = (CheckConstraint("topic IS NOT NULL OR property IS NOT NULL", name="topic_or_property"),)

    topic: Mapped[str | None] = mapped_column(String(64))
    property: Mapped[str | None] = mapped_column(String(64))
    slack_channel_id: Mapped[str] = mapped_column(String(32))
    slack_channel_name: Mapped[str | None] = mapped_column(String(80))


SKIP_RULE_TYPES = ("title_keyword", "attendee_email")


class SkipRule(Timestamped, Base):
    """Meetings matching any rule are never processed."""

    __tablename__ = "skip_rules"
    __table_args__ = (
        CheckConstraint(_in("type", SKIP_RULE_TYPES), name="type"),
        UniqueConstraint("type", "value"),
    )

    type: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(254))


MEETING_STATUSES = ("queued", "processing", "done", "partial", "failed", "skipped")


class Meeting(Timestamped, Base):
    """One row per Gemini note."""

    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(_in("status", MEETING_STATUSES), name="status"),
        Index("ix_meetings_status", "status"),
    )

    drive_file_id: Mapped[str] = mapped_column(String(128), unique=True)
    drive_modified_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    calendar_event_id: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(300))
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    properties: Mapped[list[str]] = mapped_column(JsonType, default=list)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    skip_reason: Mapped[str | None] = mapped_column(String(300))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # Kept only for reprocessing, then purged (PRD §5 Privacy).
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_text_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    attendees: Mapped[list["Attendee"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    action_items: Mapped[list["ActionItem"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    outputs: Mapped[list["Output"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    questions: Mapped[list["Question"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


class Attendee(Timestamped, Base):
    __tablename__ = "attendees"

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254))
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    meeting: Mapped[Meeting] = relationship(back_populates="attendees")


OWNER_STATUSES = ("assigned", "needs_david")
ACTION_STATUSES = ("open", "done", "dismissed")


class ActionItem(Timestamped, Base):
    """David's tasks are action items owned by David."""

    __tablename__ = "action_items"
    __table_args__ = (
        CheckConstraint(_in("owner_status", OWNER_STATUSES), name="owner_status"),
        CheckConstraint(_in("status", ACTION_STATUSES), name="status"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    # An external person named as owner (no user row); shown, never messaged.
    owner_name: Mapped[str | None] = mapped_column(String(200))
    owner_status: Mapped[str] = mapped_column(String(16), default="needs_david")
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="open")
    source_quote: Mapped[str | None] = mapped_column(Text)

    meeting: Mapped[Meeting] = relationship(back_populates="action_items")
    owner: Mapped[User | None] = relationship()


OUTPUT_TYPES = ("email_draft", "slack_dm", "slack_digest", "run_summary")
# closed_in_gmail: the Gmail draft disappeared (sent or deleted by David; the compose scope can't tell which).
OUTPUT_STATUSES = ("draft", "approved", "posted", "discarded", "failed", "closed_in_gmail")


class Output(Timestamped, Base):
    """The approval queue. The unique key makes retries safe: a second attempt updates the row, never duplicates."""

    __tablename__ = "outputs"
    __table_args__ = (
        CheckConstraint(_in("type", OUTPUT_TYPES), name="type"),
        CheckConstraint(_in("status", OUTPUT_STATUSES), name="status"),
        UniqueConstraint("meeting_id", "type", "recipient"),
        Index("ix_outputs_status", "status"),
    )

    # Null only for run summaries, which cover a whole run.
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(16))
    # Email: comma-separated addresses; Slack DM: a Slack user ID; digest: a channel ID.
    recipient: Mapped[str] = mapped_column(String(1000))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    review_carefully: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Gmail draft ID or Slack message ts.
    external_id: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    meeting: Mapped[Meeting | None] = relationship(back_populates="outputs")


QUESTION_KINDS = ("owner", "due", "other")


class Question(Timestamped, Base):
    """Up to 5 per meeting: unowned items, unclear deadlines, sensitive points. An owner or due question is tied to
    an action, and answering it updates that action (FR-35)."""

    __tablename__ = "questions"
    __table_args__ = (CheckConstraint(_in("kind", QUESTION_KINDS), name="kind"),)

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    action_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_items.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(8), default="other", server_default="other")
    text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    meeting: Mapped[Meeting] = relationship(back_populates="questions")


class Run(Timestamped, Base):
    """One row per polling run."""

    __tablename__ = "runs"

    started_at: Mapped[datetime] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    found: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


AUDIT_ACTIONS = ("approve", "edit", "discard", "answer", "reprocess", "update")


class AuditLog(Timestamped, Base):
    """Every human change: who, when, what changed."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in("action", AUDIT_ACTIONS), name="action"),
        Index("ix_audit_log_entity", "entity", "entity_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(16))
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
