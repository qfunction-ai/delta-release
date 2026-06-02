"""add skill_files table

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-05-20 20:48:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_files",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "skill_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="text/plain"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),
    )


def downgrade() -> None:
    op.drop_table("skill_files")
