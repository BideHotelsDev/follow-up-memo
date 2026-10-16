"""The AI extraction contract (PRD §6). Claude must return JSON matching SCHEMA; Extraction validates it again here.

SCHEMA is written out by hand rather than generated from the Pydantic models, because structured outputs need every
property required and additionalProperties false, which is easier to see and keep right in one place.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROPERTIES = ("The View", "The Hearth", "The Villa")
SYSTEMS = ("Mews", "Operto", "PriceLabs", "Canary", "GHL", "Xero")
NEEDS_DAVID = "NEEDS_DAVID"
MAX_QUESTIONS = 5


def _nullable(type_: str) -> dict:
    return {"type": [type_, "null"]}


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


SCHEMA = _object(
    {
        "meeting": _object(
            {
                "title": {"type": "string"},
                "purpose": {"type": "string", "description": "One sentence."},
                "properties": {"type": "array", "items": {"type": "string", "enum": list(PROPERTIES)}},
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
                        "description": f"A Bide person's first name, an external person's name, or {NEEDS_DAVID}.",
                    },
                    "due_date": {**_nullable("string"), "description": "YYYY-MM-DD, or null when no date is stated."},
                    "source_quote": {"type": "string", "description": "A short exact quote from the notes."},
                }
            ),
        },
        "open_threads": {"type": "array", "items": {"type": "string"}},
        "questions_for_david": {"type": "array", "items": {"type": "string"}},
        "systems_mentioned": {"type": "array", "items": {"type": "string", "enum": list(SYSTEMS)}},
        "notes_quality": {"type": "string", "enum": ["good", "thin", "garbled"]},
    }
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeetingInfo(_Strict):
    title: str
    purpose: str
    properties: list[Literal["The View", "The Hearth", "The Villa"]]
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
    systems_mentioned: list[Literal["Mews", "Operto", "PriceLabs", "Canary", "GHL", "Xero"]]
    notes_quality: Literal["good", "thin", "garbled"]
