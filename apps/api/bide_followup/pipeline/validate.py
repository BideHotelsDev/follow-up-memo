"""Grounding checks on Claude's extraction (PRD §9): code, not prompt, decides what is allowed through.

`check` returns problems worth one retry (Claude is told what was wrong). `ground` then makes the final extraction
safe whatever Claude did: ungrounded actions are dropped, unsupported emails and due dates are cleared, and anything
cleared becomes a question for David.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

from bide_followup.schemas.extraction import MAX_QUESTIONS, NEEDS_OWNER, ActionInfo, Extraction

EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
# Words that show a deadline was stated: weekdays, months, relative days, explicit dates and "by/before/until".
DEADLINE = re.compile(
    r"\b(mon|tues?|wed(nes)?|thu(rs)?|fri|sat(ur)?|sun)(day)?\b"
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b"
    r"|\b(today|tonight|tomorrow|week|weekend|month|eod|eow|asap|end of|by|before|until|deadline|due)\b"
    r"|\d{1,4}[/.-]\d{1,2}(?:[/.-]\d{1,4})?|\b\d{1,2}(st|nd|rd|th)\b",
    re.IGNORECASE,
)


def _normal(text: str) -> str:
    return " ".join(re.sub(r"[^\w@.]+", " ", text.lower()).split())


def grounded(quote: str, notes: str) -> bool:
    """The quote appears in the notes, allowing for spacing, punctuation and case, and small slips (a dropped word)."""
    q, n = _normal(quote), _normal(notes)
    if len(q) < 4:
        return False
    if q in n:
        return True
    match = SequenceMatcher(None, n, q, autojunk=False).find_longest_match(0, len(n), 0, len(q))
    if match.size >= 0.9 * len(q):
        return True
    # A paraphrase still counts when nearly every word is in one stretch of the notes as long as the quote.
    window = n[max(0, match.a - match.b) : match.a - match.b + int(len(q) * 1.3)]
    return SequenceMatcher(None, window, q, autojunk=False).ratio() >= 0.85


def _due(value: str | None, meeting_day: date) -> date | None:
    if value is None:
        return None
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return None
    # A due date before the meeting week or over a year out is a misreading, not a deadline.
    return day if meeting_day - timedelta(days=7) <= day <= meeting_day + timedelta(days=366) else None


def check(
    extraction: Extraction,
    notes: str,
    known_emails: set[str],
    meeting_day: date,
    properties: list[str] | None = None,
    systems: list[str] | None = None,
) -> list[str]:
    problems = []
    if properties is not None:
        unknown = [p for p in extraction.meeting.properties if p not in properties]
        if unknown:
            problems.append(f"meeting.properties has names that aren't Bide properties: {unknown}")
    if systems is not None:
        unknown = [s for s in extraction.systems_mentioned if s not in systems]
        if unknown:
            problems.append(f"systems_mentioned has names that aren't on the list: {unknown}")
    for i, action in enumerate(extraction.action_items):
        if not grounded(action.source_quote, notes):
            problems.append(f"action_items[{i}].source_quote is not a quote from the notes: {action.source_quote!r}")
        if action.due_date is not None and _due(action.due_date, meeting_day) is None:
            problems.append(f"action_items[{i}].due_date {action.due_date!r} is not a plausible YYYY-MM-DD date")
    for i, attendee in enumerate(extraction.attendees):
        if attendee.email and attendee.email.lower() not in known_emails:
            problems.append(f"attendees[{i}].email {attendee.email!r} is not in the notes or the calendar invite")
    if len(extraction.questions_for_david) > MAX_QUESTIONS:
        problems.append(f"questions_for_david has more than {MAX_QUESTIONS} questions")
    return problems


@dataclass
class GroundedAction:
    action: ActionInfo
    due: date | None


@dataclass
class Grounded:
    extraction: Extraction
    actions: list[GroundedAction]
    questions: list[tuple[str, int | None, str]]  # text, index into actions it is about, kind (owner/due/other)
    dropped: list[str] = field(default_factory=list)


def ground(
    extraction: Extraction,
    notes: str,
    known_emails: set[str],
    meeting_day: date,
    properties: list[str] | None = None,
    systems: list[str] | None = None,
) -> Grounded:
    if properties is not None:
        extraction.meeting.properties = [p for p in extraction.meeting.properties if p in properties]
    if systems is not None:
        extraction.systems_mentioned = [s for s in extraction.systems_mentioned if s in systems]
    dropped: list[str] = []
    actions: list[GroundedAction] = []
    questions: list[tuple[str, int | None, str]] = []
    for action in extraction.action_items:
        if not grounded(action.source_quote, notes):
            dropped.append(action.description)
            continue
        due = _due(action.due_date, meeting_day)
        if due is not None and not DEADLINE.search(action.source_quote):
            # Claude gave a date the quote doesn't support: keep the action, drop the date, ask.
            due = None
            questions.append((f"When is this due: {action.description}?", len(actions), "due"))
        actions.append(GroundedAction(action=action, due=due))
    for attendee in extraction.attendees:
        if attendee.email and attendee.email.lower() not in known_emails:
            attendee.email = None
    owners = [
        (f"Who should own this: {item.action.description}?", i, "owner")
        for i, item in enumerate(actions)
        if item.action.owner == NEEDS_OWNER
    ]
    # Questions tied to an action come first: answering them updates the action (FR-35).
    questions = owners + questions + [(q, None, "other") for q in extraction.questions_for_david]
    return Grounded(extraction=extraction, actions=actions, questions=questions[:MAX_QUESTIONS], dropped=dropped)


def emails_in(text: str) -> set[str]:
    return {m.lower() for m in EMAIL.findall(text)}
