"""migrate skills from letta filesystem to postgres

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-16 20:22:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content column (NOT NULL with empty string default — no existing data to preserve)
    op.add_column(
        "skills",
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
    )
    # Drop Letta filesystem columns — no longer used
    op.drop_column("skills", "letta_file_id")
    op.drop_column("skills", "letta_folder_id")
    op.drop_column("skills", "file_path")


def downgrade() -> None:
    # Restore Letta filesystem columns
    op.add_column("skills", sa.Column("file_path", sa.String(length=500), nullable=False, server_default=""))
    op.add_column("skills", sa.Column("letta_folder_id", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("skills", sa.Column("letta_file_id", sa.String(length=255), nullable=False, server_default=""))
    # Drop content column
    op.drop_column("skills", "content")
