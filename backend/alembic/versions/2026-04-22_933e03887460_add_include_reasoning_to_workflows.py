"""add include_reasoning to workflows

Revision ID: 933e03887460
Revises: d6855b645c78
Create Date: 2026-04-22 17:38:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "933e03887460"
down_revision: Union[str, None] = "d6855b645c78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("include_reasoning", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("workflows", "include_reasoning")
