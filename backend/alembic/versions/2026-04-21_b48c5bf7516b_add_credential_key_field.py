"""add credential key field

Revision ID: b48c5bf7516b
Revises: d6855b645c78
Create Date: 2026-04-21 17:14:32.175381

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b48c5bf7516b"
down_revision: Union[str, None] = "d6855b645c78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'key' column to credentials. Made idempotent because the
    # downstream migration ff8a3e6d47c6 creates the credentials table
    # with 'key' already included — so on a fresh DB this column will
    # already exist when we get here.
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'credentials' AND column_name = 'key'"
        )
    )
    if result.fetchone() is None:
        op.add_column("credentials", sa.Column("key", sa.String(length=255), nullable=False))
        op.create_index(op.f("ix_credentials_key"), "credentials", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_credentials_key"), table_name="credentials")
    op.drop_column("credentials", "key")
