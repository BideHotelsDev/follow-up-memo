"""users.sessions_valid_after, and email unique ignoring case

Revision ID: 0010
Revises: 0009

Stops with a list if two people's emails differ only by case: those have to be merged or fixed by hand first, because
sign-in matches emails ignoring case and couldn't tell them apart.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    clashes = op.get_bind().execute(
        sa.text("SELECT lower(email) AS email, count(*) AS n FROM users GROUP BY lower(email) HAVING count(*) > 1")
    ).all()
    if clashes:
        listed = ", ".join(f"{row.email} ({row.n} people)" for row in clashes)
        raise RuntimeError(f"Emails that differ only by case must be fixed in Admin > People first: {listed}")
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("sessions_valid_after", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("sessions_valid_after")
