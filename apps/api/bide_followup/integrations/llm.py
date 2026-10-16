"""Claude, for extraction (PRD decision D1). One structured-output call per meeting. Off until ANTHROPIC_API_KEY is set.

The pipeline calls `complete` and nothing else, so a different provider (the D1 fallback) would replace this file only.
Requests use `fallbacks: "default"`: if Claude's safety classifiers decline a request, the API re-runs it on
Anthropic's recommended fallback model instead of returning nothing.
"""

from dataclasses import dataclass
from typing import Any

import anthropic

from bide_followup.config import settings

FALLBACKS: dict[str, Any] = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class LlmError(Exception):
    """Claude couldn't produce a usable answer (not configured, declined, or cut off)."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def enabled() -> bool:
    return bool(settings.anthropic_api_key)


def client() -> anthropic.Anthropic:
    if not enabled():
        raise LlmError("Extraction is switched off: set ANTHROPIC_API_KEY to turn it on.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, base_url=settings.anthropic_base_url, max_retries=3)


def complete(system: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> Completion:
    """One request whose answer is JSON matching `schema`. Raises LlmError, or anthropic's errors when Claude can't be
    reached (the caller retries on the next run)."""
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
