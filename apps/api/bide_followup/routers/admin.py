"""Admin configuration: people, channel map, skip rules, settings (PRD FR-40)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from bide_followup import auth, runtime_settings
from bide_followup.db import SessionDep
from bide_followup.errors import DomainError, not_found
from bide_followup.models import ChannelMap, Run, SkipRule, User
from bide_followup.pipeline import run as pipeline
from bide_followup.schemas.api import (
    ChannelMapIn,
    ChannelMapOut,
    RunOut,
    SettingsIn,
    SettingsOut,
    SkipRuleIn,
    SkipRuleOut,
    UserIn,
    UserOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

Admin = Annotated[User, Depends(auth.require("admin"))]


@router.get("/settings")
def get_settings(session: SessionDep, _: Admin) -> SettingsOut:
    return SettingsOut(**runtime_settings.all_(session))


@router.put("/settings")
def put_settings(body: SettingsIn, session: SessionDep, _: Admin) -> SettingsOut:
    for key, value in body.model_dump(exclude_none=True).items():
        runtime_settings.put(session, key, value)
    session.commit()
    return SettingsOut(**runtime_settings.all_(session))


@router.get("/people")
def list_people(session: SessionDep, _: Admin) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in session.scalars(select(User).order_by(User.name))]


@router.post("/people", status_code=201)
def add_person(body: UserIn, session: SessionDep, _: Admin) -> UserOut:
    if session.scalar(select(User).where(func.lower(User.email) == body.email)):
        raise DomainError("email_taken", f"{body.email} is already on the list")
    user = User(**body.model_dump())
    session.add(user)
    session.commit()
    return UserOut.model_validate(user)


@router.put("/people/{user_id}")
def update_person(user_id: uuid.UUID, body: UserIn, session: SessionDep, admin: Admin) -> UserOut:
    user = session.get(User, user_id)
    if user is None:
        raise not_found("Person")
    if user.id == admin.id and (body.role != "admin" or not body.is_active):
        raise DomainError("own_access", "You can't remove your own Admin access")
    for key, value in body.model_dump().items():
        setattr(user, key, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DomainError("email_taken", f"{body.email} is already on the list")
    return UserOut.model_validate(user)


@router.get("/channels")
def list_channels(session: SessionDep, _: Admin) -> list[ChannelMapOut]:
    return [ChannelMapOut.model_validate(c) for c in session.scalars(select(ChannelMap))]


@router.put("/channels")
def replace_channels(body: list[ChannelMapIn], session: SessionDep, _: Admin) -> list[ChannelMapOut]:
    for row in body:
        if not (row.topic or row.property):
            raise DomainError("topic_or_property", "Each channel needs a topic or a property", 422)
    session.execute(delete(ChannelMap))
    rows = [ChannelMap(**row.model_dump()) for row in body]
    session.add_all(rows)
    session.commit()
    return [ChannelMapOut.model_validate(r) for r in rows]


@router.get("/skip-rules")
def list_skip_rules(session: SessionDep, _: Admin) -> list[SkipRuleOut]:
    return [SkipRuleOut.model_validate(r) for r in session.scalars(select(SkipRule))]


@router.put("/skip-rules")
def replace_skip_rules(body: list[SkipRuleIn], session: SessionDep, _: Admin) -> list[SkipRuleOut]:
    unique = {(r.type, r.value.strip().lower()) for r in body}
    session.execute(delete(SkipRule))
    rows = [SkipRule(type=t, value=v) for t, v in sorted(unique)]
    session.add_all(rows)
    session.commit()
    return [SkipRuleOut.model_validate(r) for r in rows]


@router.get("/runs")
def list_runs(session: SessionDep, _: Admin, limit: int = 50) -> list[RunOut]:
    """The run log (FR-41), newest first."""
    rows = session.scalars(select(Run).order_by(Run.started_at.desc()).limit(min(limit, 200)))
    return [RunOut.model_validate(r) for r in rows]


@router.post("/runs", status_code=201)
def run_now(session: SessionDep, _: Admin) -> RunOut:
    """Run the pipeline now rather than waiting for the worker's next poll."""
    return RunOut.model_validate(pipeline.run(session))
