"""meeting categories, editable in Admin, replacing the free-text channel topics

Revision ID: 0006
Revises: 0005
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("color", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_categories_name")),
    )
    op.add_column("meetings", sa.Column("category", sa.String(length=80), nullable=True))
    with op.batch_alter_table("channel_map", schema=None) as batch_op:
        batch_op.drop_constraint("topic_or_property", type_="check")
        batch_op.alter_column("topic", new_column_name="category", type_=sa.String(length=80))
        batch_op.create_check_constraint("category_or_property", "category IS NOT NULL OR property IS NOT NULL")
    # Each topic already mapped to a channel becomes a category, so digests keep going where they went.
    topics = [row[0] for row in op.get_bind().execute(sa.text("SELECT DISTINCT category FROM channel_map"))]
    names: dict[str, str] = {}
    for topic in sorted(t.strip() for t in topics if t and t.strip()):
        names.setdefault(topic.lower(), topic[:1].upper() + topic[1:])
    now = datetime.now(UTC)
    op.bulk_insert(
        categories,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "description": None,
                "is_sensitive": False,
                "color": i % 6,
                "sort_order": i,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for i, name in enumerate(names.values())
        ],
    )
    for lower, name in names.items():
        op.execute(
            sa.text("UPDATE channel_map SET category = :name WHERE lower(trim(category)) = :lower").bindparams(
                name=name, lower=lower
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("channel_map", schema=None) as batch_op:
        batch_op.drop_constraint("category_or_property", type_="check")
        batch_op.alter_column("category", new_column_name="topic", type_=sa.String(length=64))
        batch_op.create_check_constraint("topic_or_property", "topic IS NOT NULL OR property IS NOT NULL")
    op.drop_column("meetings", "category")
    op.drop_table("categories")
