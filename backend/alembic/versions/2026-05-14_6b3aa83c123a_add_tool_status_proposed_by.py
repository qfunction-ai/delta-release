"""add tool status proposed by

Revision ID: 6b3aa83c123a
Revises: 463267a7c548
Create Date: 2026-05-14 02:50:17.100916

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6b3aa83c123a"
down_revision: Union[str, None] = "463267a7c548"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("tools", sa.Column("proposed_by", sa.String(length=50), nullable=True))
    op.add_column("tools", sa.Column("dry_run_output", sa.Text(), nullable=True))
    op.add_column("tools", sa.Column("dry_run_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tools", "dry_run_error")
    op.drop_column("tools", "dry_run_output")
    op.drop_column("tools", "proposed_by")
    op.drop_column("tools", "status")
