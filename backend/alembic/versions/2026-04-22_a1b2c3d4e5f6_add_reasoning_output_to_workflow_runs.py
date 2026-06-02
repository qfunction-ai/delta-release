"""add reasoning_output to workflow_runs

Revision ID: a1b2c3d4e5f6
Revises: 933e03887460
Create Date: 2026-04-22 19:14:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "933e03887460"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("reasoning_output", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_runs", "reasoning_output")
