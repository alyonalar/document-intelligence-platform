from pathlib import Path

from sqlalchemy import delete, or_
from sqlmodel import Session

from app.db.models import (
    ActionItemState,
    CollectionDocumentLink,
    Document,
    DocumentEntity,
    DocumentObligation,
    DocumentRelation,
    DocumentRisk,
    ProcessingJob,
    QAInteraction,
)
from app.services.actions import action_key, split_lines
from app.services.vector_store import delete_document_chunks


def delete_document_data(session: Session, document: Document) -> Path | None:
    """Delete a document and every local artifact that belongs to it.

    Explicit cleanup keeps legacy SQLite databases safe even before the cascade
    migration is applied. The file is returned and removed only after commit.
    """
    if document.id is None:
        raise ValueError("Document is not persisted")

    document_id = document.id
    file_path = Path(document.stored_path) if document.stored_path else None
    action_keys = [action_key(document_id, text) for text in split_lines(document.action_items)]

    session.exec(
        delete(DocumentRelation).where(
            or_(
                DocumentRelation.source_document_id == document_id,
                DocumentRelation.target_document_id == document_id,
            )
        )
    )
    session.exec(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    session.exec(delete(DocumentObligation).where(DocumentObligation.document_id == document_id))
    session.exec(delete(DocumentRisk).where(DocumentRisk.document_id == document_id))
    session.exec(delete(ProcessingJob).where(ProcessingJob.document_id == document_id))
    session.exec(
        delete(CollectionDocumentLink).where(CollectionDocumentLink.document_id == document_id)
    )
    session.exec(
        delete(QAInteraction).where(QAInteraction.document_ids.contains(f",{document_id},"))
    )
    if action_keys:
        session.exec(delete(ActionItemState).where(ActionItemState.action_key.in_(action_keys)))

    session.delete(document)
    session.commit()
    delete_document_chunks(document_id)
    return file_path


def remove_stored_file(file_path: Path | None) -> None:
    if file_path and file_path.is_file():
        file_path.unlink(missing_ok=True)
