"""add source to tools

Revision ID: 02cc95e8cb46
Revises: a7b8c9d0e1f2
Create Date: 2026-05-14 01:48:44.259726

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "02cc95e8cb46"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"))


def downgrade() -> None:
    op.drop_column("tools", "source")
