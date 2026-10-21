"""Request and response bodies for the REST API (and, through OpenAPI, the web app's types)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

Role = Literal["admin", "owner", "member"]


def _domain(value: str) -> str:
    value = value.strip().lower().lstrip("@")
    if "." not in value or " " in value or "@" in value:
        raise ValueError("not an email domain")
    return value


Domain = Annotated[str, AfterValidator(_domain)]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthOut(BaseModel):
    status: str
    database: str


class ProvidersOut(BaseModel):
    google: bool
    dev: bool


class DevLoginIn(BaseModel):
    email: str


class UserOut(Orm):
    id: uuid.UUID
    email: str
    name: str
    role: Role
    slack_user_id: str | None
    ownership_areas: list[str]
    is_active: bool


class UserIn(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=120)
    role: Role = "member"
    slack_user_id: str | None = None
    ownership_areas: list[str] = []
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("not an email address")
        return v


class ConnectionOut(Orm):
    provider: Literal["google", "slack"]
    account_email: str | None
    scopes: list[str]
    status: Literal["connected", "error", "revoked"]
    last_error: str | None
    updated_at: datetime


class ConnectionsOut(BaseModel):
    google: ConnectionOut | None
    slack: ConnectionOut | None


class ChannelMapIn(BaseModel):
    category: str | None = None
    property: str | None = None
    slack_channel_id: str = Field(min_length=1)
    slack_channel_name: str | None = None


class ChannelMapOut(ChannelMapIn, Orm):
    id: uuid.UUID


class SkipRuleIn(BaseModel):
    type: Literal["title_keyword", "attendee_email"]
    value: str = Field(min_length=1, max_length=254)


class SkipRuleOut(SkipRuleIn, Orm):
    id: uuid.UUID


class SettingsOut(BaseModel):
    email_tone: str
    email_signature: str
    slack_mode: Literal["approve"]
    poll_interval_minutes: int
    minutes_saved_per_meeting: int
    baseline_followup_rate: int | None
    baseline_followup_days: float | None
    target_minutes_to_drafts: float
    target_unedited_rate: float
    target_reassigned_rate: float
    target_active_days: float
    followup_within_hours: float
    routine_stuck_hours: float
    internal_domains: list[str]
    property_region: str
    sensitive_topics: list[str]
    extract_instructions: str
    email_instructions: str
    reminders_enabled: bool
    reminder_hour: int
    weekly_digest_enabled: bool
    digest_weekday: int
    digest_hour: int
    quiet_minutes: int
    lookback_days: int
    max_attempts: int
    gmail_sync_minutes: int
    raw_text_days: int


class SettingsIn(BaseModel):
    """Only the fields sent are changed; the two baselines can be cleared by sending null."""

    email_tone: str | None = None
    email_signature: str | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=5, le=60)
    minutes_saved_per_meeting: int | None = Field(default=None, ge=1, le=240)
    baseline_followup_rate: int | None = Field(default=None, ge=0, le=100)
    baseline_followup_days: float | None = Field(default=None, ge=0, le=60)
    target_minutes_to_drafts: float | None = Field(default=None, ge=1, le=1440)
    target_unedited_rate: float | None = Field(default=None, ge=0, le=100)
    target_reassigned_rate: float | None = Field(default=None, ge=0, le=100)
    target_active_days: float | None = Field(default=None, ge=0, le=7)
    followup_within_hours: float | None = Field(default=None, ge=1, le=168)
    routine_stuck_hours: float | None = Field(default=None, ge=1, le=48)
    internal_domains: list[Domain] | None = Field(default=None, min_length=1, max_length=20)
    property_region: str | None = Field(default=None, max_length=80)
    sensitive_topics: (
        list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]] | None
    ) = Field(default=None, max_length=20)
    extract_instructions: str | None = Field(default=None, max_length=4000)
    email_instructions: str | None = Field(default=None, max_length=4000)
    reminders_enabled: bool | None = None
    reminder_hour: int | None = Field(default=None, ge=5, le=18)
    weekly_digest_enabled: bool | None = None
    digest_weekday: int | None = Field(default=None, ge=0, le=6)
    digest_hour: int | None = Field(default=None, ge=5, le=18)
    quiet_minutes: int | None = Field(default=None, ge=5, le=120)
    lookback_days: int | None = Field(default=None, ge=1, le=14)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    gmail_sync_minutes: int | None = Field(default=None, ge=10, le=240)
    raw_text_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("extract_instructions", "email_instructions")
    @classmethod
    def trim(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else None


class NoticeOut(Orm):
    id: uuid.UUID
    kind: Literal["reminder", "weekly_digest"]
    person: str
    period: date
    status: Literal["posted", "failed"]
    error: str | None
    attempts: int
    updated_at: datetime


class PreviewOut(BaseModel):
    text: str


class RunOut(Orm):
    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    found: int
    processed: int
    skipped: int
    failed: int
    error: str | None


# --- review (PRD §8 Internal REST API) ---------------------------------------------------------------------------

Bucket = Literal["late", "today", "week", "later", "nodate", "done"]
MeetingStatus = Literal["queued", "processing", "waiting", "done", "partial", "failed", "skipped"]
OutputType = Literal["email_draft", "slack_dm", "slack_digest", "run_summary"]
OutputStatus = Literal["draft", "approved", "posted", "discarded", "failed", "closed_in_gmail"]


class PersonOut(Orm):
    id: uuid.UUID
    name: str
    role: Role


class AttendeeOut(Orm):
    name: str
    email: str | None
    is_internal: bool


class MeetingRef(BaseModel):
    id: uuid.UUID
    title: str
    started_at: datetime | None
    properties: list[str]
    category: str | None


class TaskOut(BaseModel):
    id: uuid.UUID
    meeting: MeetingRef
    description: str
    owner: PersonOut | None
    owner_name: str | None  # an external person named in the notes
    owner_status: Literal["assigned", "needs_david"]
    due_date: date | None
    status: Literal["open", "done", "dismissed"]
    source_quote: str | None
    bucket: Bucket


class TaskIn(BaseModel):
    """Only the fields sent are changed. owner_user_id null (with the field sent) makes the task Needs David."""

    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None
    status: Literal["open", "done", "dismissed"] | None = None


class QuestionOut(BaseModel):
    id: uuid.UUID
    meeting: MeetingRef
    kind: Literal["owner", "due", "other"]
    text: str
    action_item_id: uuid.UUID | None
    answer: str | None
    answered_at: datetime | None


class AnswerIn(BaseModel):
    """owner questions take owner_user_id, due questions due_date, the rest text."""

    owner_user_id: uuid.UUID | None = None
    due_date: date | None = None
    text: str | None = Field(default=None, max_length=2000)


class OutputOut(BaseModel):
    id: uuid.UUID
    meeting: MeetingRef | None
    type: OutputType
    recipient: str
    recipient_label: str
    subject: str | None
    body: str
    review_carefully: bool
    status: OutputStatus
    error: str | None
    gmail_url: str | None
    approved_at: datetime | None
    updated_at: datetime


class OutputIn(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20000)


class ApproveAllIn(BaseModel):
    """Approve every Slack draft of one meeting, or (no meeting) every Slack draft waiting."""

    meeting_id: uuid.UUID | None = None


class MeetingSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    started_at: datetime | None
    ended_at: datetime | None
    properties: list[str]
    category: str | None
    status: MeetingStatus
    skip_reason: str | None
    is_sensitive: bool
    attendee_count: int
    action_count: int
    open_questions: int
    drafts_waiting: int


class MeetingOut(MeetingSummaryOut):
    notes_url: str
    purpose: str | None
    key_points: list[str]
    decisions: list[str]
    open_threads: list[str]
    systems_mentioned: list[str]
    notes_quality: str | None
    dropped_actions: list[str]
    error: str | None
    prompt_version: str | None
    attendees: list[AttendeeOut]
    tasks: list[TaskOut]
    questions: list[QuestionOut]
    outputs: list[OutputOut]


class TodayCounts(BaseModel):
    questions: int
    emails: int
    slack: int
    tasks_open: int
    tasks_overdue: int


class TodayOut(BaseModel):
    date: date
    viewer: PersonOut
    counts: TodayCounts
    meetings: list[MeetingSummaryOut]
    questions: list[QuestionOut]
    next_tasks: list[TaskOut]
    problems: list[MeetingSummaryOut]
    last_run: RunOut | None
    next_run_at: datetime | None


# --- impact ------------------------------------------------------------------------------------------------------


class ImpactWeek(BaseModel):
    week_start: date
    meetings: int
    followed_up: int
    rate: int | None
    in_progress: bool


class ImpactActions(BaseModel):
    on_time: int
    late: int
    open: int
    overdue: int
    on_time_rate: int | None


class ImpactOwner(BaseModel):
    name: str
    open: int
    overdue: int


class ImpactDrafts(BaseModel):
    acted: int
    unedited: int
    reassigned: int
    actions: int


class ImpactHotel(BaseModel):
    name: str
    meetings: int
    followed_up_rate: int | None
    actions: int
    on_time_rate: int | None
    overdue: int


class ImpactTargets(BaseModel):
    target_minutes_to_drafts: float
    target_unedited_rate: float
    target_reassigned_rate: float
    target_active_days: float
    followup_within_hours: float
    routine_stuck_hours: float


class ImpactOut(BaseModel):
    since: date
    weeks: list[ImpactWeek]
    meetings: int
    followed_up: int
    followed_up_rate: int | None
    minutes_to_drafts: float | None
    minutes_to_follow_up: float | None
    actions: ImpactActions
    owners: list[ImpactOwner]
    drafts: ImpactDrafts
    meetings_handled: int
    david_active_days: int
    minutes_saved_per_meeting: int
    baseline_followup_rate: int | None
    baseline_followup_days: float | None
    targets: ImpactTargets
    owner_name: str
    hotels: list[ImpactHotel]


# --- service API (the Claude Code routine) -----------------------------------------------------------------------


class LlmJobOut(BaseModel):
    id: uuid.UUID
    kind: Literal["extract", "email"]
    system: str
    messages: list[dict]
    schema_: dict = Field(alias="schema", serialization_alias="schema")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LlmAnswerIn(BaseModel):
    text: str = Field(min_length=2, max_length=200_000, description="The JSON answer, exactly as the schema asks")
    model: str | None = Field(default=None, max_length=64)


class LlmFailIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class QueueOut(BaseModel):
    pending: int
    oldest_pending_at: datetime | None


class ClaudeStatusOut(BaseModel):
    mode: Literal["api", "routine"]
    enabled: bool
    model: str
    pending: int
    oldest_pending_at: datetime | None
    last_answer_at: datetime | None


# --- what Bide edits in Admin (catalog.py) -----------------------------------------------------------------------


class PropertyOut(Orm):
    id: uuid.UUID
    name: str
    color: int
    sort_order: int
    is_active: bool


class PropertyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def strip(cls, v: str) -> str:
        return " ".join(v.split())


class CategoryOut(Orm):
    id: uuid.UUID
    name: str
    description: str | None
    is_sensitive: bool
    color: int
    sort_order: int
    is_active: bool


class CategoryIn(PropertyIn):
    description: str | None = Field(default=None, max_length=300)
    is_sensitive: bool = False


class SystemOut(Orm):
    id: uuid.UUID
    name: str
    is_active: bool


class SystemIn(PropertyIn):
    """Same fields as a property."""


class PipelineOut(BaseModel):
    """How the app is set to run, for How it works and the Impact definitions."""

    poll_interval_minutes: int
    quiet_minutes: int
    gmail_sync_minutes: int
    max_attempts: int
    raw_text_days: int
    internal_domains: list[str]
    sensitive_topics: list[str]
    reminders_enabled: bool
    reminder_hour: int
    weekly_digest_enabled: bool
    digest_weekday: int
    digest_hour: int
    skip_rules: int
    channels: int


class AppOut(BaseModel):
    """What the web app needs on every page: the owner's name, the properties (with their tag colours), the systems,
    and how the pipeline is set to run. The categories include those switched off, so past meetings keep their colour."""

    owner_name: str
    owner_email: str | None
    people: list[str]
    properties: list[PropertyOut]
    categories: list[CategoryOut]
    systems: list[str]
    pipeline: PipelineOut
