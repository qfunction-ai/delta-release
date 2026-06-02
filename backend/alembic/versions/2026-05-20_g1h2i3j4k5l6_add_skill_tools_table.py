"""add skill_tools table

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-20 22:37:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skill_tools",
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tool_id", UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("skill_tools")
