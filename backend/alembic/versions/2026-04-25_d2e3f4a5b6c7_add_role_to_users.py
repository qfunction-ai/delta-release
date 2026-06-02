"""add_role_to_users

Revision ID: d2e3f4a5b6c7
Revises: 77f53116e134
Create Date: 2026-04-25 00:23:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "77f53116e134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(50), nullable=False, server_default="user"))
    # Set existing users to admin (they were created before the role system)
    op.execute("UPDATE users SET role = 'admin'")


def downgrade() -> None:
    op.drop_column("users", "role")
