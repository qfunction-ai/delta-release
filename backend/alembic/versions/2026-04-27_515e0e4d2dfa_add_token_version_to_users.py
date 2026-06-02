"""add token_version to users

Revision ID: 515e0e4d2dfa
Revises: f6a7b8c9d0e1
Create Date: 2026-04-27 00:46:59.200948

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "515e0e4d2dfa"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("users", "token_version")
