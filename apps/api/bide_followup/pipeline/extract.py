"""Stage 3, Extract (PRD §6): one Claude call with the note, the Bide context and the schema; validate; retry once with
what was wrong; then ground the result so nothing unsupported gets through (pipeline/validate.py)."""

import json
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup import catalog, runtime_settings
from bide_followup.integrations import llm
from bide_followup.models import User
from bide_followup.pipeline import validate
from bide_followup.schemas.extraction import Extraction, schema

PROMPT_VERSION = "extract_v3"
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


class ExtractionFailed(Exception):
    """Claude's answer still didn't match the schema after the retry."""


@cache
def _template(version: str) -> str:
    return (PROMPTS / f"{version}.md").read_text()


def system_prompt(session: Session) -> str:
    """The prompt plus the Bide context from Admin settings. Sorted, so it only changes when the settings do."""
    people = session.scalars(select(User).where(User.is_active).order_by(User.name)).all()
    lines = []
    for p in people:
        areas = f"; owns {', '.join(p.ownership_areas)}" if p.ownership_areas else ""
        lines.append(f"- {p.name} ({p.email}), {p.role}{areas}")
    categories = [f"- {c.name}" + (f": {c.description}" if c.description else "") for c in catalog.categories(session)]
    names = catalog.property_names(session)
    where = runtime_settings.in_region(session)
    if len(names) > 1:
        listed = f"{len(names)} short-stay properties{where}: {_and(names)}"
    else:
        listed = f"a short-stay property{where}: {names[0]}" if names else f"short-stay properties{where}"
    sensitive = runtime_settings.get(session, "sensitive_topics")
    prompt = _template(PROMPT_VERSION).format(
        owner=catalog.owner_name(session),
        properties=listed,
        people="\n".join(lines) or "- (none listed)",
        domains=" or ".join(f"@{d}" for d in runtime_settings.domains(session)),
        categories="\n".join(categories) or "- (none listed: use null)",
        sensitive=_and(sensitive, "or") if sensitive else "anything the owner would not want shared with the team",
    )
    return runtime_settings.with_instructions(session, prompt, "extract_instructions")


def _and(words: list[str], last: str = "and") -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} {last} {words[-1]}"


def user_message(title: str, meeting_day: date, attendees: list[tuple[str, str]], notes: str) -> str:
    invite = "\n".join(f"- {name} <{email}>" for name, email in attendees) or "(no calendar invite found)"
    return (
        f"Meeting: {title}\nMeeting date: {meeting_day.isoformat()} ({meeting_day:%A})\n\n"
        f"Calendar invite attendees:\n{invite}\n\n<notes>\n{notes}\n</notes>"
    )


@dataclass
class Result:
    grounded: validate.Grounded
    input_tokens: int
    output_tokens: int


def _parse(text: str) -> tuple[Extraction | None, list[str]]:
    try:
        return Extraction.model_validate_json(text), []
    except ValidationError as exc:
        return None, [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:20]]


def extract(
    session: Session,
    title: str,
    meeting_day: date,
    attendees: list[tuple[str, str]],
    notes: str,
    meeting_id=None,
) -> Result:
    system = system_prompt(session)
    messages = [{"role": "user", "content": user_message(title, meeting_day, attendees, notes)}]
    known_emails = validate.emails_in(notes) | {email for _, email in attendees}
    properties, systems = catalog.property_names(session), catalog.system_names(session)
    categories = catalog.category_names(session)
    answer_schema = schema(properties, systems, categories)
    tokens_in = tokens_out = 0

    for attempt in range(2):
        completion = llm.complete(
            system, messages, answer_schema, session=session, kind="extract", meeting_id=meeting_id
        )
        tokens_in += completion.input_tokens
        tokens_out += completion.output_tokens
        extraction, problems = _parse(completion.text)
        if extraction is not None:
            problems = validate.check(extraction, notes, known_emails, meeting_day, properties, systems, categories)
        if not problems or (extraction is not None and attempt == 1):
            break
        # Append-only: the first answer stays in the conversation, followed by what was wrong with it.
        messages += [
            {"role": "assistant", "content": completion.text},
            {
                "role": "user",
                "content": "That answer has problems. Fix them and answer again with the whole JSON:\n"
                + "\n".join(f"- {p}" for p in problems),
            },
        ]
    if extraction is None:
        raise ExtractionFailed("; ".join(problems)[:1000])
    return Result(
        grounded=validate.ground(extraction, notes, known_emails, meeting_day, properties, systems, categories),
        input_tokens=tokens_in,
        output_tokens=tokens_out,
    )


def summary(extraction: Extraction) -> dict:
    """What `meetings.extraction` keeps (the full JSON; it is the meeting's summary, not the notes)."""
    return json.loads(extraction.model_dump_json())
