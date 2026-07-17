"""remove web_search_enabled and docs_fetch_enabled from user settings

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-07-17 02:19:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user_settings", "web_search_enabled")
    op.drop_column("user_settings", "docs_fetch_enabled")


def downgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("web_search_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "user_settings",
        sa.Column("docs_fetch_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
