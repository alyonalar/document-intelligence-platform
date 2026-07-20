import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app import seed_demo
from app.db.engine import engine
from app.db.models import Collection, CollectionDocumentLink, Document, QAInteraction
from app.seed_demo import DEMO_COLLECTION_NAME, DEMO_DOCUMENTS, seed_demo_data
from app.services.actions import list_document_actions


def test_seed_demo_data_creates_showcase_workspace():
    with Session(engine) as session:
        result = seed_demo_data(session)

        documents = session.exec(
            select(Document).where(
                Document.filename.in_([item["filename"] for item in DEMO_DOCUMENTS])
            )
        ).all()
        collection = session.exec(
            select(Collection).where(Collection.name == DEMO_COLLECTION_NAME)
        ).first()
        history = session.exec(select(QAInteraction).where(QAInteraction.model == "demo")).all()
        actions = [
            action
            for action in list_document_actions(session, completion_status="all")
            if action.filename in {item["filename"] for item in DEMO_DOCUMENTS}
        ]

    assert result["documents"] == len(DEMO_DOCUMENTS)
    assert len(documents) == len(DEMO_DOCUMENTS)
    assert collection is not None
    assert len(history) >= 2
    assert sum(1 for action in actions if action.completed) == 1
    assert sum(1 for action in actions if action.note) == 1
    assert all(document.processing_status == "ready" for document in documents)
    assert all(document.raw_text for document in documents)


def test_seed_demo_data_is_idempotent():
    filenames = [item["filename"] for item in DEMO_DOCUMENTS]

    with Session(engine) as session:
        seed_demo_data(session)
        seed_demo_data(session)

        documents = session.exec(select(Document).where(Document.filename.in_(filenames))).all()
        collection = session.exec(
            select(Collection).where(Collection.name == DEMO_COLLECTION_NAME)
        ).first()
        links = session.exec(
            select(CollectionDocumentLink).where(
                CollectionDocumentLink.collection_id == collection.id
            )
        ).all()
        history = session.exec(select(QAInteraction).where(QAInteraction.model == "demo")).all()
        actions = [
            action
            for action in list_document_actions(session, completion_status="all")
            if action.filename in filenames
        ]

    assert len(documents) == len(DEMO_DOCUMENTS)
    assert len(links) == len(DEMO_DOCUMENTS)
    assert len(history) == 2
    assert sum(1 for action in actions if action.completed) == 1
    assert sum(1 for action in actions if action.note) == 1


def test_seed_demo_requires_alembic_migrated_database(monkeypatch, tmp_path):
    temporary_engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(seed_demo, "engine", temporary_engine)
    monkeypatch.setattr(seed_demo, "alembic_head_revision", lambda: "head-revision")

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        seed_demo.ensure_database_migrated()
