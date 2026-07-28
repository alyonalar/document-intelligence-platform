from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from app.core.config import settings
from app.db.engine import engine
from app.db.models import (
    ActionItemState,
    Collection,
    CollectionDocumentLink,
    Document,
    QAInteraction,
)
from app.services.actions import list_document_actions, set_action_item_note, set_action_item_status
from app.services.document_processing import process_document
from app.services.history import save_qa_interaction, serialize_document_ids, serialize_sources

DEMO_COLLECTION_NAME = "Demo: Document Intelligence"
ALEMBIC_INI_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"

DEMO_DOCUMENTS = [
    {
        "filename": "demo-contract-alpha.txt",
        "title": "Contract INT-2026-001 with TOO Romashka",
        "content": (
            "Contract no. INT-2026-001 between TOO Romashka and Atlas LLP. The agreement starts on 2026-01-10. "
            "Atlas LLP must pay 150000 KZT no later than 2026-02-01. "
            "TOO Romashka should provide implementation report by 2026-01-25. "
            "The contract includes confidentiality, liability, penalty of 10% for late payment, and automatic renewal. "
            "Either party may request termination by 2026-12-15."
        ),
    },
    {
        "filename": "demo-invoice-alpha.txt",
        "title": "Invoice INV-2026-045 referencing contract INT-2026-001",
        "content": (
            "Invoice # INV-2026-045 for TOO Romashka references contract no. INT-2026-001. "
            "Atlas LLP must pay 150000 KZT no later than 2024-02-01. "
            "Finance should send a reminder if payment is not received. Late payment may trigger penalty."
        ),
    },
    {
        "filename": "demo-act-alpha.txt",
        "title": "Act ACT-2026-010 for contract INT-2026-001",
        "content": (
            "Act № ACT-2026-010 confirms services under contract no. INT-2026-001. "
            "TOO Romashka and Atlas LLP signed the act on 2026-01-30. "
            "Customer should submit objections within 5 days. The amount is 150000 KZT."
        ),
    },
    {
        "filename": "demo-policy-alpha.txt",
        "title": "Document Handling Policy",
        "content": (
            "Policy document for contract operations. What are payment deadlines? Payment deadlines are tracked from invoices and obligations. "
            "What risks should legal review? Legal should review liability, confidentiality, auto-renewal, termination, and penalty clauses. "
            "Operations should provide documents to Finance within 3 days."
        ),
    },
]


def demo_upload_dir() -> Path:
    return Path(settings.upload_dir) / "demo"


def alembic_head_revision() -> str:
    config = Config(str(ALEMBIC_INI_PATH))
    return ScriptDirectory.from_config(config).get_current_head()


def ensure_database_migrated() -> None:
    """Require Alembic migrations instead of creating schema implicitly."""
    expected_head = alembic_head_revision()
    with engine.connect() as connection:
        table_names = inspect(connection).get_table_names()
        if "alembic_version" not in table_names:
            raise RuntimeError(
                "Database schema is not initialized by Alembic. "
                "Run `alembic upgrade head` before `python -m app.seed_demo`."
            )

        revisions = (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        )

    if expected_head not in revisions:
        current = ", ".join(revisions) if revisions else "none"
        raise RuntimeError(
            "Database schema is not at Alembic head "
            f"({current} != {expected_head}). "
            "Run `alembic upgrade head` before `python -m app.seed_demo`."
        )


def upsert_demo_document(session: Session, item: dict) -> Document:
    upload_dir = demo_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / item["filename"]
    file_path.write_text(item["content"], encoding="utf-8")

    document = session.exec(select(Document).where(Document.filename == item["filename"])).first()

    if document is None:
        document = Document(
            filename=item["filename"],
            stored_path=str(file_path),
            file_type="txt",
            file_size=file_path.stat().st_size,
            title=item["title"],
            processing_status="queued",
        )
    else:
        document.stored_path = str(file_path)
        document.file_type = "txt"
        document.file_size = file_path.stat().st_size
        document.title = item["title"]
        document.processing_status = "queued"
        document.processing_error = None

    session.add(document)
    session.commit()
    session.refresh(document)

    process_document(session, document)
    session.refresh(document)
    return document


def upsert_demo_collection(session: Session, documents: list[Document]) -> Collection:
    collection = session.exec(
        select(Collection).where(Collection.name == DEMO_COLLECTION_NAME)
    ).first()
    if collection is None:
        collection = Collection(
            name=DEMO_COLLECTION_NAME,
            description="Demo workspace with documents, dates, actions, sources, and history.",
        )
        session.add(collection)
        session.commit()
        session.refresh(collection)

    for document in documents:
        if collection.id is None or document.id is None:
            continue
        existing = session.exec(
            select(CollectionDocumentLink).where(
                CollectionDocumentLink.collection_id == collection.id,
                CollectionDocumentLink.document_id == document.id,
            )
        ).first()
        if existing:
            continue
        session.add(
            CollectionDocumentLink(
                collection_id=collection.id,
                document_id=document.id,
            )
        )

    session.commit()
    session.refresh(collection)
    return collection


def upsert_demo_history(session: Session, documents: list[Document]) -> None:
    document_ids = [document.id for document in documents if document.id is not None]
    if not document_ids:
        return

    first_document = next((document for document in documents if document.id is not None), None)
    if first_document is None:
        return

    questions = [
        {
            "scope": "workspace",
            "question": "What obligations and risks exist across the demo documents?",
            "answer": (
                "Atlas LLP must pay 150000 KZT, TOO Romashka should provide an implementation report, "
                "the customer should submit objections within 5 days, and operations should provide documents to Finance. "
                "The main risks are penalty, late payment, confidentiality, liability, auto-renewal, and termination."
            ),
            "document_ids": document_ids,
            "retrieval": "demo-seed",
            "sources": [
                {
                    "document_id": first_document.id,
                    "filename": first_document.filename,
                    "chunk_index": 1,
                    "text": "Atlas LLP must pay 150000 KZT no later than 2026-02-01.",
                }
            ],
        },
        {
            "scope": "document",
            "question": "Which dates are mentioned in the demo contract?",
            "answer": "The contract mentions 2026-01-10, 2026-02-01, 2026-01-25, and 2026-12-15.",
            "document_ids": [first_document.id],
            "retrieval": "demo-seed",
            "sources": [
                {
                    "document_id": first_document.id,
                    "filename": first_document.filename,
                    "chunk_index": 1,
                    "text": "The agreement starts on 2026-01-10.",
                }
            ],
        },
    ]

    for item in questions:
        existing = session.exec(
            select(QAInteraction).where(QAInteraction.question == item["question"])
        ).first()
        if existing:
            existing.scope = item["scope"]
            existing.answer = item["answer"]
            existing.document_ids = serialize_document_ids(item["document_ids"])
            existing.model = "demo"
            existing.retrieval = item["retrieval"]
            existing.sources = serialize_sources(item["sources"])
            session.add(existing)
            continue
        save_qa_interaction(
            session=session,
            scope=item["scope"],
            question=item["question"],
            answer=item["answer"],
            document_ids=item["document_ids"],
            model="demo",
            retrieval=item["retrieval"],
            sources=item["sources"],
        )

    session.commit()


def apply_demo_action_states(session: Session) -> None:
    demo_filenames = {item["filename"] for item in DEMO_DOCUMENTS}
    all_actions = list_document_actions(session, completion_status="all")
    demo_actions = [action for action in all_actions if action.filename in demo_filenames]

    for action in demo_actions:
        existing = session.exec(
            select(ActionItemState).where(ActionItemState.action_key == action.action_key)
        ).first()
        if existing:
            session.delete(existing)
    session.commit()

    all_actions = list_document_actions(session, completion_status="all")
    demo_actions = [action for action in all_actions if action.filename in demo_filenames]

    done_action = next(
        (
            action
            for action in demo_actions
            if "implementation report" in action.text.lower() or "provide" in action.text.lower()
        ),
        None,
    )
    if done_action:
        set_action_item_status(session, done_action.action_key, "done")

    noted_action = next(
        (
            action
            for action in demo_actions
            if "pay" in action.text.lower() or "payment" in action.text.lower()
        ),
        None,
    )
    if noted_action:
        set_action_item_status(session, noted_action.action_key, "open")
        set_action_item_note(
            session,
            noted_action.action_key,
            "Demo note: payment obligation is tracked by the intelligence engine.",
            "2026-02-01",
        )


def seed_demo_data(session: Session | None = None) -> dict:
    owns_session = session is None
    session = session or Session(engine)
    try:
        documents = [upsert_demo_document(session, item) for item in DEMO_DOCUMENTS]
        collection = upsert_demo_collection(session, documents)
        upsert_demo_history(session, documents)
        apply_demo_action_states(session)
        actions = list_document_actions(session, completion_status="all")
        return {
            "documents": len(documents),
            "collection": collection.name,
            "actions": len(actions),
        }
    finally:
        if owns_session:
            session.close()


def main() -> None:
    ensure_database_migrated()
    result = seed_demo_data()
    print(
        "Seeded demo data: "
        f"{result['documents']} documents, collection '{result['collection']}', "
        f"{result['actions']} action item(s)."
    )


if __name__ == "__main__":
    main()
