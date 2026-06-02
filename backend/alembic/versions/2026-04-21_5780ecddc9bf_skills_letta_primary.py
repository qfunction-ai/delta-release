"""skills letta primary

Revision ID: 5780ecddc9bf
Revises: 956150604bab
Create Date: 2026-04-21 14:00:50.531984

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "5780ecddc9bf"
down_revision: Union[str, None] = "956150604bab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The initial migration (956150604bab) already created the skills table.
    # This migration alters it: makes letta_file_id/letta_folder_id NOT NULL,
    # drops the content column, and changes description from Text to String(1000).
    op.alter_column("skills", "letta_file_id", existing_type=sa.String(length=255), nullable=False)
    op.alter_column("skills", "letta_folder_id", existing_type=sa.String(length=255), nullable=False)
    op.alter_column(
        "skills", "description", existing_type=sa.Text(), type_=sa.String(length=1000), existing_nullable=True
    )
    op.drop_column("skills", "content")


def downgrade() -> None:
    op.add_column("skills", sa.Column("content", sa.Text(), nullable=False))
    op.alter_column(
        "skills", "description", existing_type=sa.String(length=1000), type_=sa.Text(), existing_nullable=True
    )
    op.alter_column("skills", "letta_folder_id", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("skills", "letta_file_id", existing_type=sa.String(length=255), nullable=True)
