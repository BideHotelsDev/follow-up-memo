"""Claude Code routine: llm_jobs and the waiting meeting status

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
OLD = "status IN ('queued', 'processing', 'done', 'partial', 'failed', 'skipped')"
NEW = "status IN ('queued', 'processing', 'waiting', 'done', 'partial', 'failed', 'skipped')"


def upgrade() -> None:
    op.create_table(
        "llm_jobs",
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("messages", JSON, nullable=False),
        sa.Column("schema", JSON, nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('extract', 'email')", name=op.f("ck_llm_jobs_kind")),
        sa.CheckConstraint("status IN ('pending', 'answered', 'failed')", name=op.f("ck_llm_jobs_status")),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"], name=op.f("fk_llm_jobs_meeting_id_meetings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_jobs")),
        sa.UniqueConstraint("request_hash", name=op.f("uq_llm_jobs_request_hash")),
    )
    op.create_index("ix_llm_jobs_status", "llm_jobs", ["status"])
    with op.batch_alter_table("meetings", schema=None) as batch_op:
        batch_op.drop_constraint("status", type_="check")
        batch_op.create_check_constraint("status", NEW)


def downgrade() -> None:
    op.execute("UPDATE meetings SET status = 'queued' WHERE status = 'waiting'")
    with op.batch_alter_table("meetings", schema=None) as batch_op:
        batch_op.drop_constraint("status", type_="check")
        batch_op.create_check_constraint("status", OLD)
    op.drop_index("ix_llm_jobs_status", table_name="llm_jobs")
    op.drop_table("llm_jobs")
