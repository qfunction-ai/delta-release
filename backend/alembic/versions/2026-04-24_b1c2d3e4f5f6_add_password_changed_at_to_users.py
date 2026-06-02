"""add password_changed_at to users

Revision ID: b1c2d3e4f5f6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24

"""

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5f6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
