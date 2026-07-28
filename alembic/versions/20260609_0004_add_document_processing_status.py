"""add document processing status

Revision ID: 20260609_0004
Revises: 20260609_0003
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260609_0004"
down_revision: Union[str, Sequence[str], None] = "20260609_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("processing_status", sa.String(), nullable=False, server_default="ready"),
    )
    op.add_column("document", sa.Column("processing_error", sa.String(), nullable=True))
    op.add_column(
        "document",
        sa.Column("indexed_chunks", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("document", "indexed_chunks")
    op.drop_column("document", "processing_error")
    op.drop_column("document", "processing_status")
