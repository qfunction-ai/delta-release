"""add eval_enabled to user settings

Revision ID: a1b2c3d4e5f7
Revises: 6b3aa83c123a
Create Date: 2026-05-15 02:11:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "6b3aa83c123a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("eval_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "eval_enabled")
