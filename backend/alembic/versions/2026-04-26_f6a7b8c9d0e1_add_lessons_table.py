"""Add lessons table for execution feedback loop.

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-04-26

Stores lessons extracted from workflow runs — strategy, recovery,
and optimization insights that are injected into future executions
to improve agent performance over time.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers
revision = "f6a7b8c9d0e1"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lessons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "workflow_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("utility_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("times_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("lessons")
