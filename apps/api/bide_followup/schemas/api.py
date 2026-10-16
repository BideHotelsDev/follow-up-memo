"""Request and response bodies for the REST API (and, through OpenAPI, the web app's types)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["admin", "owner", "member"]


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
    topic: str | None = None
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


class SettingsIn(BaseModel):
    """Only the fields sent are changed; the two baselines can be cleared by sending null."""

    email_tone: str | None = None
    email_signature: str | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=5, le=60)
    minutes_saved_per_meeting: int | None = Field(default=None, ge=1, le=240)
    baseline_followup_rate: int | None = Field(default=None, ge=0, le=100)
    baseline_followup_days: float | None = Field(default=None, ge=0, le=60)


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
MeetingStatus = Literal["queued", "processing", "done", "partial", "failed", "skipped"]
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
    hotels: list[ImpactHotel]
