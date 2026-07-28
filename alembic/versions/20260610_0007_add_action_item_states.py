"""add action item states

Revision ID: 20260610_0007
Revises: 20260610_0006
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0007"
down_revision: Union[str, Sequence[str], None] = "20260610_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actionitemstate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_actionitemstate_action_key", "actionitemstate", ["action_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_actionitemstate_action_key", table_name="actionitemstate")
    op.drop_table("actionitemstate")
