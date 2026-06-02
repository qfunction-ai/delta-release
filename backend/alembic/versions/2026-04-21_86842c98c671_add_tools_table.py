"""add tools table

Revision ID: 86842c98c671
Revises: 5780ecddc9bf
Create Date: 2026-04-21 14:12:12.283173

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "86842c98c671"
down_revision: Union[str, None] = "5780ecddc9bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("letta_tool_id", sa.String(length=255), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("json_schema", sa.Text(), nullable=False),
        sa.Column("tags", sa.String(length=500), nullable=True),
        sa.Column("pip_requirements", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_tools_user_name"),
    )
    op.create_index(op.f("ix_tools_user_id"), "tools", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tools_user_id"), table_name="tools")
    op.drop_table("tools")
