"""properties and systems, editable in Admin

Revision ID: 0005
Revises: 0004
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# What was fixed in the code until now, so nothing changes on upgrade.
PROPERTIES = ("The View", "The Hearth", "The Villa")
SYSTEMS = ("Mews", "Operto", "PriceLabs", "Canary", "GHL", "Xero")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    properties = op.create_table(
        "properties",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_properties")),
        sa.UniqueConstraint("name", name=op.f("uq_properties_name")),
    )
    systems = op.create_table(
        "systems",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_systems")),
        sa.UniqueConstraint("name", name=op.f("uq_systems_name")),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        properties,
        [
            {
                "id": uuid.uuid4(),
                "name": n,
                "color": i,
                "sort_order": i,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for i, n in enumerate(PROPERTIES)
        ],
    )
    op.bulk_insert(
        systems,
        [{"id": uuid.uuid4(), "name": n, "is_active": True, "created_at": now, "updated_at": now} for n in SYSTEMS],
    )


def downgrade() -> None:
    op.drop_table("systems")
    op.drop_table("properties")
