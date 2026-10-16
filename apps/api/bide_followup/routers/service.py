"""The service API for the Claude Code routine (EXTRACTION_MODE=routine): fetch the Claude requests waiting in the
queue, answer them, then ask for a run so the answers turn into drafts straight away. routine/README.md has the
routine's instructions.

Authenticated with a bearer token (SERVICE_API_TOKEN). Requests carry meeting notes, so the token is a secret: keep
it in the routine's environment, never in a prompt or a repository.
"""

import json
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select

from bide_followup import clock
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.errors import DomainError, not_found
from bide_followup.models import LlmJob
from bide_followup.pipeline import run as pipeline
from bide_followup.schemas.api import LlmAnswerIn, LlmFailIn, LlmJobOut, QueueOut, RunOut


def service_token(authorization: Annotated[str, Header()] = "") -> None:
    if not settings.service_api_token:
        raise HTTPException(status_code=503, detail="The service API is not configured (SERVICE_API_TOKEN)")
    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token.encode(), settings.service_api_token.encode()):
        raise HTTPException(status_code=401, detail="invalid service token")


router = APIRouter(prefix="/api/service/v1", tags=["service"], dependencies=[Depends(service_token)])


def _job(session, job_id: uuid.UUID) -> LlmJob:
    job = session.get(LlmJob, job_id)
    if job is None:
        raise not_found("Job")
    if job.status != "pending":
        raise DomainError("already_answered", "This request was already answered")
    return job


@router.get("/queue")
def queue(session: SessionDep) -> QueueOut:
    pending = select(LlmJob).where(LlmJob.status == "pending")
    return QueueOut(
        pending=session.scalar(select(func.count()).select_from(pending.subquery())) or 0,
        oldest_pending_at=session.scalar(select(func.min(LlmJob.created_at)).where(LlmJob.status == "pending")),
    )


@router.get("/llm-jobs")
def jobs(session: SessionDep, limit: Annotated[int, Query(ge=1, le=20)] = 5) -> list[LlmJobOut]:
    """The oldest Claude requests waiting for an answer. Each is a system prompt, a conversation and a JSON schema:
    answer it as the API would, with JSON matching the schema and nothing else."""
    rows = session.scalars(
        select(LlmJob).where(LlmJob.status == "pending").order_by(LlmJob.created_at).limit(limit)
    ).all()
    for job in rows:
        job.claimed_at = clock.utcnow()
    session.commit()
    return [LlmJobOut.model_validate(job) for job in rows]


@router.post("/llm-jobs/{job_id}/answer", status_code=204)
def answer(job_id: uuid.UUID, body: LlmAnswerIn, session: SessionDep) -> None:
    """Store an answer. It must parse as JSON; the pipeline then checks it against the schema and the notes exactly
    as it checks an API answer, and asks again (a new request) when something is wrong."""
    job = _job(session, job_id)
    text = body.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise DomainError("not_json", f"The answer isn't valid JSON ({exc.msg}); send only the JSON", 422)
    job.answer, job.model = text, body.model or "claude-code-routine"
    job.status, job.answered_at = "answered", clock.utcnow()
    session.commit()


@router.post("/llm-jobs/{job_id}/fail", status_code=204)
def fail(job_id: uuid.UUID, body: LlmFailIn, session: SessionDep) -> None:
    """Give up on a request (for example, Claude declined it). The meeting counts an attempt and is asked again."""
    job = _job(session, job_id)
    job.status, job.error = "failed", body.reason
    session.commit()


@router.post("/run", status_code=201)
def run_now(session: SessionDep) -> RunOut:
    """Run the pipeline now, so answers just given become drafts and David's summary without waiting for the
    worker's next poll."""
    return RunOut.model_validate(pipeline.run(session))
