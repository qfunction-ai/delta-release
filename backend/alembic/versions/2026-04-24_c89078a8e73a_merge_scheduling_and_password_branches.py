"""merge scheduling and password branches

Revision ID: c89078a8e73a
Revises: b4c44ae395b9, b1c2d3e4f5f6
Create Date: 2026-04-24 14:32:12.478504

"""

from typing import Sequence, Union

revision: str = "c89078a8e73a"
down_revision: Union[str, None] = ("b4c44ae395b9", "b1c2d3e4f5f6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
