"""notices: the weekly nudge about open tasks with no due date

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notices") as batch:
        batch.drop_constraint(op.f("ck_notices_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_notices_kind"), "kind IN ('reminder', 'weekly_digest', 'undated_nudge')")


def downgrade() -> None:
    op.execute("DELETE FROM notices WHERE kind = 'undated_nudge'")
    with op.batch_alter_table("notices") as batch:
        batch.drop_constraint(op.f("ck_notices_kind"), type_="check")
        batch.create_check_constraint(op.f("ck_notices_kind"), "kind IN ('reminder', 'weekly_digest')")
