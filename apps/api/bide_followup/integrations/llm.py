"""Claude, for extraction and email writing (PRD decision D1). One structured-output request at a time.

Two ways to reach Claude, chosen by EXTRACTION_MODE:

- "api": the Claude API, with ANTHROPIC_API_KEY. Requests use `fallbacks: "default"`: if Claude's safety
  classifiers decline a request, the API re-runs it on Anthropic's recommended fallback model.
- "routine": a scheduled Claude Code routine on Bide's Claude plan answers queued requests through the service API
  (routers/service.py). `complete` looks the request up by its hash: answered, it returns the answer; otherwise it
  queues it and raises Pending, and the pipeline tries again on a later run. Requests are built deterministically
  from the meeting, so the retry asks the same question and finds the answer.

The pipeline calls `complete` and nothing else.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from bide_followup.config import settings
from bide_followup.models import LlmJob

FALLBACKS: dict[str, Any] = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class LlmError(Exception):
    """Claude couldn't produce a usable answer (not configured, declined, or cut off)."""


class Pending(Exception):
    """Routine mode: the request is queued for the Claude Code routine. Try again on a later run."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def routine() -> bool:
    return settings.extraction_mode == "routine"


def enabled() -> bool:
    return bool(settings.service_api_token) if routine() else bool(settings.anthropic_api_key)


def off_reason() -> str:
    if routine():
        return "Extraction is off (SERVICE_API_TOKEN not set for the Claude Code routine); meetings wait in the queue"
    return "Extraction is off (ANTHROPIC_API_KEY not set); meetings wait in the queue"


def client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise LlmError("Extraction is switched off: set ANTHROPIC_API_KEY to turn it on.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, base_url=settings.anthropic_base_url, max_retries=3)


def request_hash(system: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> str:
    body = json.dumps({"system": system, "messages": messages, "schema": schema}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def _from_queue(
    session: Session, kind: str, meeting_id: uuid.UUID | None, system: str, messages: list, schema: dict
) -> Completion:
    key = request_hash(system, messages, schema)
    job = session.scalar(select(LlmJob).where(LlmJob.request_hash == key))
    if job is None:
        session.add(
            LlmJob(meeting_id=meeting_id, kind=kind, request_hash=key, system=system, messages=messages, schema=schema)
        )
        session.flush()
        raise Pending(kind)
    if job.status == "pending":
        raise Pending(kind)
    if job.status == "failed":
        # The run loop clears failed requests after recording the failure, so the next attempt asks again.
        raise LlmError(f"Claude Code routine: {job.error or 'the routine could not answer'}")
    return Completion(text=job.answer or "", model=job.model or "claude-code-routine", input_tokens=0, output_tokens=0)


def complete(
    system: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    session: Session | None = None,
    kind: str = "extract",
    meeting_id: uuid.UUID | None = None,
) -> Completion:
    """One request whose answer is JSON matching `schema`. Raises LlmError, Pending (routine mode), or anthropic's
    errors when Claude can't be reached (the caller retries on the next run)."""
    if routine():
        if session is None:
            raise LlmError("Routine mode needs the database session")
        return _from_queue(session, kind, meeting_id, system, messages, schema)
    response = client().beta.messages.create(
        model=settings.llm_model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": settings.llm_effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=messages,
        **FALLBACKS,
    )
    # Refusals and truncation come back as a normal response; read stop_reason before trusting the content.
    if response.stop_reason == "refusal":
        raise LlmError("Claude declined this request, and the fallback model did too.")
    if response.stop_reason == "max_tokens":
        raise LlmError("Claude's answer was cut off before it finished.")
    text = "".join(block.text for block in response.content if block.type == "text")
    return Completion(
        text=text,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
