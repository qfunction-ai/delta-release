"""Change credential key uniqueness from global to per-user.

Revision ID: e4f5a6b7c8d9
Revises: d2e3f4a5b6c7
Create Date: 2026-04-25

The `key` column previously had a global unique constraint, preventing
different users from using the same credential key name. This changes
the constraint to (user_id, key) so keys are scoped per user.
"""

from alembic import op

# revision identifiers
revision = "e4f5a6b7c8d9"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old global unique constraint on `key`
    op.drop_constraint("credentials_key_key", "credentials", type_="unique")

    # Add the new composite unique constraint (user_id, key)
    op.create_unique_constraint("uq_credentials_user_key", "credentials", ["user_id", "key"])


def downgrade() -> None:
    # Drop the composite constraint
    op.drop_constraint("uq_credentials_user_key", "credentials", type_="unique")

    # Restore the global unique constraint on `key`
    op.create_unique_constraint("credentials_key_key", "credentials", ["key"])
