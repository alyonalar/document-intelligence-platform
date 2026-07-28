"""enable cascade deletes for document-owned records

Revision ID: 20260717_0013
Revises: 20260702_0012
Create Date: 2026-07-17
"""

from alembic import op

revision = "20260717_0013"
down_revision = "20260702_0012"
branch_labels = None
depends_on = None


NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


FOREIGN_KEYS = {
    "collectiondocumentlink": [
        ("collection_id", "collection", "id"),
        ("document_id", "document", "id"),
    ],
    "processingjob": [("document_id", "document", "id")],
    "documententity": [("document_id", "document", "id")],
    "documentrelation": [
        ("source_document_id", "document", "id"),
        ("target_document_id", "document", "id"),
        ("source_entity_id", "documententity", "id"),
        ("target_entity_id", "documententity", "id"),
    ],
    "documentobligation": [("document_id", "document", "id")],
    "documentrisk": [("document_id", "document", "id")],
}


def _replace_foreign_keys(*, ondelete: str | None) -> None:
    for table_name, foreign_keys in FOREIGN_KEYS.items():
        with op.batch_alter_table(
            table_name,
            recreate="always",
            naming_convention=NAMING_CONVENTION,
        ) as batch_op:
            for column, target_table, target_column in foreign_keys:
                name = f"fk_{table_name}_{column}_{target_table}"
                batch_op.drop_constraint(name, type_="foreignkey")
                batch_op.create_foreign_key(
                    name,
                    target_table,
                    [column],
                    [target_column],
                    ondelete=ondelete,
                )


def upgrade() -> None:
    _replace_foreign_keys(ondelete="CASCADE")


def downgrade() -> None:
    _replace_foreign_keys(ondelete=None)
