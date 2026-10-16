"""question kind

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16 19:38:24.796763
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing questions predate kinds; "other" leaves them answerable as free text.
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(length=8), nullable=False, server_default="other"))
        batch_op.create_check_constraint("kind", "kind IN ('owner', 'due', 'other')")


def downgrade() -> None:
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_constraint("kind", type_="check")
        batch_op.drop_column("kind")
