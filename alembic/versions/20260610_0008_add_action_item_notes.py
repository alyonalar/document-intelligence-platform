"""add action item notes

Revision ID: 20260610_0008
Revises: 20260610_0007
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0008"
down_revision: Union[str, Sequence[str], None] = "20260610_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("actionitemstate", sa.Column("note", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("actionitemstate", "note")
