"""The AI extraction contract (PRD §6). Claude must return JSON matching the schema; Extraction validates it again.

The schema is written out by hand rather than generated from the Pydantic models, because structured outputs need
every property required and additionalProperties false, which is easier to see and keep right in one place. The
category, property and system lists come from Admin (catalog.py), so `schema()` builds it for the current ones.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NEEDS_OWNER = "NEEDS_OWNER"  # an action with no clear owner, for the owner (David) to assign
MAX_QUESTIONS = 5


def _nullable(type_: str) -> dict:
    return {"type": [type_, "null"]}


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _names(names: list[str]) -> dict:
    # An enum needs at least one value; with none configured, any string (the checks in validate.py still apply).
    return {"type": "string", "enum": list(names)} if names else {"type": "string"}


def _one_of(names: list[str]) -> dict:
    return {"anyOf": [{"type": "string", "enum": list(names)}, {"type": "null"}]} if names else _nullable("string")


def schema(properties: list[str], systems: list[str], categories: list[str] | None = None) -> dict:
    return _object(
        {
            "meeting": _object(
                {
                    "title": {"type": "string"},
                    "purpose": {"type": "string", "description": "One sentence."},
                    "category": _one_of(categories or []),
                    "properties": {"type": "array", "items": _names(properties)},
                    "is_sensitive": {"type": "boolean"},
                    "sensitive_reason": _nullable("string"),
                }
            ),
            "attendees": {
                "type": "array",
                "items": _object(
                    {"name": {"type": "string"}, "email": _nullable("string"), "is_internal": {"type": "boolean"}}
                ),
            },
            "key_points": {"type": "array", "items": {"type": "string"}},
            "decisions": {"type": "array", "items": {"type": "string"}},
            "action_items": {
                "type": "array",
                "items": _object(
                    {
                        "description": {"type": "string"},
                        "owner": {
                            "type": "string",
                            "description": f"A Bide person's first name, an external person's name, or {NEEDS_OWNER}.",
                        },
                        "due_date": {
                            **_nullable("string"),
                            "description": "YYYY-MM-DD, or null when no date is stated.",
                        },
                        "source_quote": {"type": "string", "description": "A short exact quote from the notes."},
                    }
                ),
            },
            "open_threads": {"type": "array", "items": {"type": "string"}},
            "questions_for_david": {"type": "array", "items": {"type": "string"}},
            "systems_mentioned": {"type": "array", "items": _names(systems)},
            "notes_quality": {"type": "string", "enum": ["good", "thin", "garbled"]},
        }
    )


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeetingInfo(_Strict):
    title: str
    purpose: str
    category: str | None = None  # absent from extractions made before categories
    properties: list[str]
    is_sensitive: bool
    sensitive_reason: str | None


class AttendeeInfo(_Strict):
    name: str
    email: str | None
    is_internal: bool


class ActionInfo(_Strict):
    description: str = Field(min_length=1)
    owner: str
    due_date: str | None
    source_quote: str


class Extraction(_Strict):
    meeting: MeetingInfo
    attendees: list[AttendeeInfo]
    key_points: list[str]
    decisions: list[str]
    action_items: list[ActionInfo]
    open_threads: list[str]
    questions_for_david: list[str]
    systems_mentioned: list[str]
    notes_quality: Literal["good", "thin", "garbled"]
