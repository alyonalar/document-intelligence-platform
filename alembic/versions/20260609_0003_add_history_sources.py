"""add history sources

Revision ID: 20260609_0003
Revises: 20260605_0002
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260609_0003"
down_revision: Union[str, Sequence[str], None] = "20260605_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("qainteraction", sa.Column("sources", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("qainteraction", "sources")
