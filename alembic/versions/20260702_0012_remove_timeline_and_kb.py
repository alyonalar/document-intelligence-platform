"""remove timeline and knowledge base draft tables

Revision ID: 20260702_0012
Revises: 20260629_0011
Create Date: 2026-07-02
"""

import sqlalchemy as sa

from alembic import op

revision = "20260702_0012"
down_revision = "20260629_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("knowledgebaseitem")
    op.drop_table("documenttimelineevent")


def downgrade() -> None:
    op.create_table(
        "documenttimelineevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.DateTime(), nullable=True),
        sa.Column("event_date_text", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["document_id", "event_date", "event_type"]:
        op.create_index(
            op.f(f"ix_documenttimelineevent_{column}"),
            "documenttimelineevent",
            [column],
            unique=False,
        )

    op.create_table(
        "knowledgebaseitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.String(), nullable=False),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=True),
        sa.Column("source_document_ids", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["document_id", "collection_id", "status"]:
        op.create_index(
            op.f(f"ix_knowledgebaseitem_{column}"), "knowledgebaseitem", [column], unique=False
        )
