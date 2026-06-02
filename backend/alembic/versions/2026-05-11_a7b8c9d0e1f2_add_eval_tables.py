"""Add eval_scenarios and eval_runs tables.

Revision ID: a7b8c9d0e1f2
Revises: 515e0e4d2dfa
Create Date: 2026-05-11

Stores eval scenario definitions and their execution results
for agent evaluation via giskard-checks.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers
revision = "a7b8c9d0e1f2"
down_revision = "515e0e4d2dfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_scenarios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_eval_scenarios_user_name"),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("eval_scenarios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("eval_scenarios")
