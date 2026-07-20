"""add document intelligence

Revision ID: 20260629_0011
Revises: 20260611_0010
Create Date: 2026-06-29 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260629_0011"
down_revision: Union[str, None] = "20260611_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("intelligence_status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column("document", sa.Column("intelligence_error", sa.String(), nullable=True))
    op.add_column("document", sa.Column("intelligence_processed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "documententity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("normalized_value", sa.String(), nullable=True),
        sa.Column("source_text", sa.String(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_documententity_document_id"), "documententity", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_documententity_entity_type"), "documententity", ["entity_type"], unique=False
    )
    op.create_index(
        op.f("ix_documententity_normalized_value"),
        "documententity",
        ["normalized_value"],
        unique=False,
    )

    op.create_table(
        "documentrelation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("target_document_id", sa.Integer(), nullable=True),
        sa.Column("source_entity_id", sa.Integer(), nullable=True),
        sa.Column("target_entity_id", sa.Integer(), nullable=True),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column("evidence_text", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["target_document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["source_entity_id"], ["documententity.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["documententity.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "source_document_id",
        "target_document_id",
        "source_entity_id",
        "target_entity_id",
        "relation_type",
    ]:
        op.create_index(
            op.f(f"ix_documentrelation_{column}"), "documentrelation", [column], unique=False
        )

    op.create_table(
        "documentobligation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("object", sa.String(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("due_date_text", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["document_id", "due_date", "status"]:
        op.create_index(
            op.f(f"ix_documentobligation_{column}"), "documentobligation", [column], unique=False
        )

    op.create_table(
        "documentrisk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("risk_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["document_id", "risk_type", "severity"]:
        op.create_index(op.f(f"ix_documentrisk_{column}"), "documentrisk", [column], unique=False)

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

    op.create_table(
        "entityalias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("canonical_value", sa.String(), nullable=False),
        sa.Column("alias_value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["entity_type", "canonical_value", "alias_value"]:
        op.create_index(op.f(f"ix_entityalias_{column}"), "entityalias", [column], unique=False)


def downgrade() -> None:
    op.drop_table("entityalias")
    op.drop_table("knowledgebaseitem")
    op.drop_table("documenttimelineevent")
    op.drop_table("documentrisk")
    op.drop_table("documentobligation")
    op.drop_table("documentrelation")
    op.drop_table("documententity")
    op.drop_column("document", "intelligence_processed_at")
    op.drop_column("document", "intelligence_error")
    op.drop_column("document", "intelligence_status")
