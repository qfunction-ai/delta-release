"""rename credential fields to unified taxonomy

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-20 18:12:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename credential columns to unified taxonomy
    op.alter_column("credentials", "api_url", new_column_name="url")
    op.alter_column("credentials", "api_key_encrypted", new_column_name="primary_key_encrypted")
    op.alter_column("credentials", "api_secret_encrypted", new_column_name="secondary_key_encrypted")


def downgrade() -> None:
    # Revert to old column names
    op.alter_column("credentials", "secondary_key_encrypted", new_column_name="api_secret_encrypted")
    op.alter_column("credentials", "primary_key_encrypted", new_column_name="api_key_encrypted")
    op.alter_column("credentials", "url", new_column_name="api_url")
