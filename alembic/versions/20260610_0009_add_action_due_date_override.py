"""add action due date override

Revision ID: 20260610_0009
Revises: 20260610_0008
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0009"
down_revision: Union[str, Sequence[str], None] = "20260610_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("actionitemstate", sa.Column("due_date_override", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("actionitemstate", "due_date_override")
