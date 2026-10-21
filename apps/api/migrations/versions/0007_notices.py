"""notices: due-date reminders and the weekly digest

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("recipient", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('reminder', 'weekly_digest')", name=op.f("ck_notices_kind")),
        sa.CheckConstraint("status IN ('posted', 'failed')", name=op.f("ck_notices_status")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_notices_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
        sa.UniqueConstraint("kind", "user_id", "period", name=op.f("uq_notices_kind")),
    )


def downgrade() -> None:
    op.drop_table("notices")
