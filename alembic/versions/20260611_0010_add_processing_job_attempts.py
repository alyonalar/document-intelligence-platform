"""add processing job attempts

Revision ID: 20260611_0010
Revises: 20260610_0009
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260611_0010"
down_revision: Union[str, Sequence[str], None] = "20260610_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "processingjob",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("processingjob", "attempts")
