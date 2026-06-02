"""add user settings table

Revision ID: 463267a7c548
Revises: 02cc95e8cb46
Create Date: 2026-05-14 02:49:57.802778

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "463267a7c548"
down_revision: Union[str, None] = "02cc95e8cb46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_tool_creation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="user_settings_pkey"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
