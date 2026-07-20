"""initial schema

Revision ID: 20260605_0001
Revises: None
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260605_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("stored_path", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("raw_text", sa.String(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("estimated_reading_time_min", sa.Integer(), nullable=False),
        sa.Column("summary_short", sa.String(), nullable=True),
        sa.Column("key_points", sa.String(), nullable=True),
        sa.Column("bullet_summary", sa.String(), nullable=True),
        sa.Column("keywords", sa.String(), nullable=True),
        sa.Column("llm_summary", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "qainteraction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("document_ids", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("retrieval", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("qainteraction")
    op.drop_table("document")
