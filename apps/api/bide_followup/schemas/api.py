"""Request and response bodies for the REST API (and, through OpenAPI, the web app's types)."""

import uuid
from datetime import datetime
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


class SettingsIn(BaseModel):
    email_tone: str | None = None
    email_signature: str | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=5, le=60)
