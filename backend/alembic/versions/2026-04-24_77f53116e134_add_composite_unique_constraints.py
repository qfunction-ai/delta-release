"""add_composite_unique_constraints

Revision ID: 77f53116e134
Revises: c89078a8e73a
Create Date: 2026-04-24 18:02:20.492566

"""

from typing import Sequence, Union

from alembic import op

revision: str = "77f53116e134"
down_revision: Union[str, None] = "c89078a8e73a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_skills_user_name", "skills", ["user_id", "name"])
    op.create_unique_constraint("uq_tools_user_name", "tools", ["user_id", "name"])
    op.create_unique_constraint("uq_workflows_user_name", "workflows", ["user_id", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_workflows_user_name", "workflows", type_="unique")
    op.drop_constraint("uq_tools_user_name", "tools", type_="unique")
    op.drop_constraint("uq_skills_user_name", "skills", type_="unique")
