import json

from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.models import QAInteraction


def serialize_document_ids(document_ids: list[int]) -> str:
    if not document_ids:
        return ""
    return "," + ",".join(str(doc_id) for doc_id in document_ids) + ","


def serialize_sources(sources: list[dict] | list[str] | None) -> str | None:
    if not sources:
        return None
    return json.dumps(sources, ensure_ascii=False)


def deserialize_sources(sources: str | None) -> list:
    if not sources:
        return []
    try:
        value = json.loads(sources)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def attach_sources(interactions: list[QAInteraction]) -> list[dict]:
    return [
        {
            "item": interaction,
            "sources": deserialize_sources(interaction.sources),
        }
        for interaction in interactions
    ]


def save_qa_interaction(
    session: Session,
    scope: str,
    question: str,
    answer: str,
    document_ids: list[int],
    model: str | None = None,
    retrieval: str | None = None,
    sources: list[dict] | list[str] | None = None,
) -> QAInteraction:
    interaction = QAInteraction(
        scope=scope,
        question=question,
        answer=answer,
        document_ids=serialize_document_ids(document_ids),
        model=model,
        retrieval=retrieval,
        sources=serialize_sources(sources),
    )
    session.add(interaction)
    session.commit()
    session.refresh(interaction)
    return interaction


def list_recent_interactions(session: Session, limit: int = 10) -> list[QAInteraction]:
    statement = select(QAInteraction).order_by(QAInteraction.created_at.desc()).limit(limit)
    return session.exec(statement).all()


def list_document_interactions(
    session: Session,
    document_id: int,
    limit: int = 8,
) -> list[QAInteraction]:
    statement = (
        select(QAInteraction)
        .where(QAInteraction.document_ids.contains(f",{document_id},"))
        .order_by(QAInteraction.created_at.desc())
        .limit(limit)
    )
    return session.exec(statement).all()


def search_interactions(
    session: Session,
    query: str = "",
    scope: str = "",
    limit: int = 50,
) -> list[QAInteraction]:
    statement = select(QAInteraction)

    if query.strip():
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                QAInteraction.question.like(pattern),
                QAInteraction.answer.like(pattern),
            )
        )

    if scope.strip():
        statement = statement.where(QAInteraction.scope == scope.strip())

    statement = statement.order_by(QAInteraction.created_at.desc()).limit(limit)
    return session.exec(statement).all()
