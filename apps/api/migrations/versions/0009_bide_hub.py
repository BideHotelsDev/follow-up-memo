"""Sign in with Bide: users.bide_hub_sub and hub_logouts

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("bide_hub_sub", sa.String(length=64), nullable=True))
        batch.create_unique_constraint(op.f("uq_users_bide_hub_sub"), ["bide_hub_sub"])
    op.create_table(
        "hub_logouts",
        sa.Column("sid", sa.String(length=64), nullable=True),
        sa.Column("sub", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hub_logouts")),
    )
    op.create_index(op.f("ix_hub_logouts_sid"), "hub_logouts", ["sid"])
    op.create_index(op.f("ix_hub_logouts_sub"), "hub_logouts", ["sub"])


def downgrade() -> None:
    op.drop_table("hub_logouts")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("uq_users_bide_hub_sub"), type_="unique")
        batch.drop_column("bide_hub_sub")
