"""add web_search_enabled to user settings

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-05-16 19:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "web_search_enabled")
