"""add document insights

Revision ID: 20260610_0006
Revises: 20260609_0005
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260610_0006"
down_revision: Union[str, Sequence[str], None] = "20260609_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document", sa.Column("document_type", sa.String(), nullable=True))
    op.add_column("document", sa.Column("detected_dates", sa.String(), nullable=True))
    op.add_column("document", sa.Column("action_items", sa.String(), nullable=True))
    op.add_column("document", sa.Column("suggested_questions", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "suggested_questions")
    op.drop_column("document", "action_items")
    op.drop_column("document", "detected_dates")
    op.drop_column("document", "document_type")
