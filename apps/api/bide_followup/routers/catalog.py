"""Properties, categories and systems (Admin → Properties, Categories), and the app settings every page reads."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bide_followup import auth, catalog, runtime_settings
from bide_followup.auth import CurrentUser
from bide_followup.db import SessionDep
from bide_followup.errors import DomainError, not_found
from bide_followup.models import Category, ChannelMap, Meeting, Property, SkipRule, System, User
from bide_followup.schemas.api import (
    AppOut,
    CategoryIn,
    CategoryOut,
    PipelineOut,
    PropertyIn,
    PropertyOut,
    SystemIn,
    SystemOut,
)

router = APIRouter(prefix="/api", tags=["catalog"])

# David (owner) and Kyle (admin) both run Admin.
Admin = Annotated[User, Depends(auth.require("owner", "admin"))]
TAG_COLOURS = 6  # tag colour slots defined in the web app's index.css


@router.get("/app")
def app_settings(session: SessionDep, _: CurrentUser) -> AppOut:
    owner = catalog.owner(session)
    values = runtime_settings.all_(session)

    def count(model) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    return AppOut(
        owner_name=catalog.owner_name(session),
        owner_email=owner.email if owner else None,
        people=list(session.scalars(select(User.name).where(User.is_active).order_by(User.name))),
        properties=[PropertyOut.model_validate(p) for p in catalog.properties(session)],
        categories=[CategoryOut.model_validate(c) for c in catalog.categories(session, active_only=False)],
        systems=catalog.system_names(session),
        pipeline=PipelineOut(
            **{key: values[key] for key in PipelineOut.model_fields if key in values},
            skip_rules=count(SkipRule),
            channels=count(ChannelMap),
        ),
    )


def _name_taken(session: Session, model, name: str, exclude: uuid.UUID | None = None) -> bool:
    query = select(model).where(func.lower(model.name) == name.lower())
    if exclude:
        query = query.where(model.id != exclude)
    return session.scalar(query) is not None


def _next_slot(existing, sort_order: int | None) -> tuple[int, int]:
    """A new row's tag colour (the first free slot) and place (the end of the list unless given)."""
    used = {row.color for row in existing}
    colour = next((c for c in range(TAG_COLOURS) if c not in used), len(existing) % TAG_COLOURS)
    order = sort_order if sort_order is not None else max((row.sort_order for row in existing), default=-1) + 1
    return colour, order


@router.get("/admin/properties")
def list_properties(session: SessionDep, _: Admin) -> list[PropertyOut]:
    return [PropertyOut.model_validate(p) for p in catalog.properties(session, active_only=False)]


@router.post("/admin/properties", status_code=201)
def add_property(body: PropertyIn, session: SessionDep, _: Admin) -> PropertyOut:
    if _name_taken(session, Property, body.name):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    colour, order = _next_slot(catalog.properties(session, active_only=False), body.sort_order)
    row = Property(name=body.name, color=colour, sort_order=order, is_active=body.is_active)
    session.add(row)
    session.commit()
    return PropertyOut.model_validate(row)


@router.put("/admin/properties/{property_id}")
def update_property(property_id: uuid.UUID, body: PropertyIn, session: SessionDep, _: Admin) -> PropertyOut:
    """Rename, hide or reorder a property. A rename carries over to every meeting and channel tagged with it."""
    row = session.get(Property, property_id)
    if row is None:
        raise not_found("Property")
    if _name_taken(session, Property, body.name, exclude=row.id):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    if body.name != row.name:
        old = row.name
        for meeting in session.scalars(select(Meeting)):
            if old in (meeting.properties or []):
                meeting.properties = [body.name if p == old else p for p in meeting.properties]
        for channel in session.scalars(select(ChannelMap).where(ChannelMap.property == old)):
            channel.property = body.name
        row.name = body.name
    row.is_active = body.is_active
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    session.commit()
    return PropertyOut.model_validate(row)


@router.get("/admin/categories")
def list_categories(session: SessionDep, _: Admin) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in catalog.categories(session, active_only=False)]


@router.post("/admin/categories", status_code=201)
def add_category(body: CategoryIn, session: SessionDep, _: Admin) -> CategoryOut:
    if _name_taken(session, Category, body.name):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    colour, order = _next_slot(catalog.categories(session, active_only=False), body.sort_order)
    row = Category(
        name=body.name,
        description=_text(body.description),
        is_sensitive=body.is_sensitive,
        color=colour,
        sort_order=order,
        is_active=body.is_active,
    )
    session.add(row)
    session.commit()
    return CategoryOut.model_validate(row)


@router.put("/admin/categories/{category_id}")
def update_category(category_id: uuid.UUID, body: CategoryIn, session: SessionDep, _: Admin) -> CategoryOut:
    """Rename, describe, mark sensitive, hide or reorder a category. A rename carries over to its meetings and
    channel. Marking it sensitive applies to meetings processed from now on."""
    row = session.get(Category, category_id)
    if row is None:
        raise not_found("Category")
    if _name_taken(session, Category, body.name, exclude=row.id):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    if body.name != row.name:
        for meeting in session.scalars(select(Meeting).where(Meeting.category == row.name)):
            meeting.category = body.name
        for channel in session.scalars(select(ChannelMap).where(ChannelMap.category == row.name)):
            channel.category = body.name
        row.name = body.name
    row.description, row.is_sensitive, row.is_active = _text(body.description), body.is_sensitive, body.is_active
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    session.commit()
    return CategoryOut.model_validate(row)


def _text(value: str | None) -> str | None:
    return " ".join(value.split()) or None if value else None


@router.get("/admin/systems")
def list_systems(session: SessionDep, _: Admin) -> list[SystemOut]:
    return [SystemOut.model_validate(s) for s in session.scalars(select(System).order_by(System.name))]


@router.post("/admin/systems", status_code=201)
def add_system(body: SystemIn, session: SessionDep, _: Admin) -> SystemOut:
    if _name_taken(session, System, body.name):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    row = System(name=body.name, is_active=body.is_active)
    session.add(row)
    session.commit()
    return SystemOut.model_validate(row)


@router.put("/admin/systems/{system_id}")
def update_system(system_id: uuid.UUID, body: SystemIn, session: SessionDep, _: Admin) -> SystemOut:
    row = session.get(System, system_id)
    if row is None:
        raise not_found("System")
    if _name_taken(session, System, body.name, exclude=row.id):
        raise DomainError("name_taken", f"{body.name} is already on the list")
    row.name, row.is_active = body.name, body.is_active
    session.commit()
    return SystemOut.model_validate(row)
