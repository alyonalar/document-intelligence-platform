"""add processing jobs

Revision ID: 20260609_0005
Revises: 20260609_0004
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260609_0005"
down_revision: Union[str, Sequence[str], None] = "20260609_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processingjob",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("processingjob")
