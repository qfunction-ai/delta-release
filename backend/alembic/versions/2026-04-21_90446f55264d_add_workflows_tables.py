"""add workflows tables

Revision ID: 90446f55264d
Revises: 86842c98c671
Create Date: 2026-04-21 14:38:21.815866

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "90446f55264d"
down_revision: Union[str, None] = "86842c98c671"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_workflows_user_name"),
    )
    op.create_index(op.f("ix_workflows_user_id"), "workflows", ["user_id"], unique=False)

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("input_variables", sa.Text(), nullable=True),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("letta_run_id", sa.String(length=255), nullable=True),
        sa.Column("steps_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_runs_workflow_id"), "workflow_runs", ["workflow_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_runs_workflow_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index(op.f("ix_workflows_user_id"), table_name="workflows")
    op.drop_table("workflows")
