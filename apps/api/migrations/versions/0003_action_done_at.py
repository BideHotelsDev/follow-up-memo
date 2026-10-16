"""action done_at

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("action_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("done_at", sa.DateTime(timezone=True), nullable=True))
    # Tasks already done: the last change is the best record of when.
    op.execute("UPDATE action_items SET done_at = updated_at WHERE status = 'done'")


def downgrade() -> None:
    with op.batch_alter_table("action_items", schema=None) as batch_op:
        batch_op.drop_column("done_at")
