"""add credential key

Revision ID: ff8a3e6d47c6
Revises: b48c5bf7516b
Create Date: 2026-04-21 17:16:00.192061

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "ff8a3e6d47c6"
down_revision: Union[str, None] = "b48c5bf7516b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # These tables were NOT created by any earlier migration.
    # The original autogenerate dump included duplicate create_table calls
    # for skills, tools, workflows, and workflow_runs (already created by
    # 956150604bab, 86842c98c671, 90446f55264d respectively). Those have
    # been removed — only the genuinely new tables remain.

    op.create_table(
        "agents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("letta_agent_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("embedding", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("letta_agent_id"),
    )
    op.create_index(op.f("ix_agents_user_id"), "agents", ["user_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("api_url", sa.String(length=500), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credentials_key"), "credentials", ["key"], unique=True)
    op.create_index(op.f("ix_credentials_user_id"), "credentials", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_credentials_user_id"), table_name="credentials")
    op.drop_index(op.f("ix_credentials_key"), table_name="credentials")
    op.drop_table("credentials")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_agents_user_id"), table_name="agents")
    op.drop_table("agents")
