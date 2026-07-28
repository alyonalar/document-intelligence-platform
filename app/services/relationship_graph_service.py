from sqlalchemy import delete, or_
from sqlmodel import Session, select

from app.db.models import Document, DocumentEntity, DocumentRelation

RELATION_BY_ENTITY = {
    "organization": "same_party",
    "contract_number": "references_contract",
    "invoice_number": "references_invoice",
    "act_number": "references_act",
    "date": "related_by_date",
    "amount": "related_by_amount",
}


def _relation_exists(
    session: Session,
    source_id: int,
    target_id: int,
    relation_type: str,
    source_entity_id: int | None,
) -> bool:
    return bool(
        session.exec(
            select(DocumentRelation)
            .where(DocumentRelation.source_document_id == source_id)
            .where(DocumentRelation.target_document_id == target_id)
            .where(DocumentRelation.relation_type == relation_type)
            .where(DocumentRelation.source_entity_id == source_entity_id)
        ).first()
    )


def build_relations_for_document(
    session: Session,
    document_id: int,
    *,
    commit: bool = True,
) -> list[DocumentRelation]:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")

    session.exec(
        delete(DocumentRelation).where(
            or_(
                DocumentRelation.source_document_id == document_id,
                DocumentRelation.target_document_id == document_id,
            )
        )
    )
    entities = session.exec(
        select(DocumentEntity).where(DocumentEntity.document_id == document_id)
    ).all()
    created = []
    for entity in entities:
        relation_type = RELATION_BY_ENTITY.get(entity.entity_type, "mentions")
        if entity.id is not None:
            mention = DocumentRelation(
                source_document_id=document_id,
                target_document_id=None,
                source_entity_id=entity.id,
                relation_type="mentions",
                evidence_text=entity.source_text or entity.value,
                confidence=entity.confidence,
            )
            session.add(mention)
            created.append(mention)
        if not entity.normalized_value:
            continue
        matches = session.exec(
            select(DocumentEntity)
            .where(DocumentEntity.document_id != document_id)
            .where(DocumentEntity.entity_type == entity.entity_type)
            .where(DocumentEntity.normalized_value == entity.normalized_value)
        ).all()
        for target in matches:
            if target.document_id == document_id or _relation_exists(
                session, document_id, target.document_id, relation_type, entity.id
            ):
                continue
            relation = DocumentRelation(
                source_document_id=document_id,
                target_document_id=target.document_id,
                source_entity_id=entity.id,
                target_entity_id=target.id,
                relation_type=relation_type,
                evidence_text=f"Shared {entity.entity_type}: {entity.value}",
                confidence=min(entity.confidence or 0.7, target.confidence or 0.7),
            )
            session.add(relation)
            created.append(relation)
    if commit:
        session.commit()
    else:
        session.flush()
    for relation in created:
        session.refresh(relation)
    return created


def rebuild_workspace_graph(session: Session) -> list[DocumentRelation]:
    session.exec(delete(DocumentRelation))
    session.commit()
    relations = []
    documents = session.exec(select(Document)).all()
    for document in documents:
        if document.id is not None:
            relations.extend(build_relations_for_document(session, document.id))
    return relations


def find_related_documents(session: Session, document_id: int) -> list[Document]:
    relations = session.exec(
        select(DocumentRelation).where(
            or_(
                DocumentRelation.source_document_id == document_id,
                DocumentRelation.target_document_id == document_id,
            )
        )
    ).all()
    related_ids = {
        relation.target_document_id
        if relation.source_document_id == document_id
        else relation.source_document_id
        for relation in relations
    }
    related_ids.discard(None)
    if not related_ids:
        return []
    return session.exec(select(Document).where(Document.id.in_(related_ids))).all()


def get_document_graph(session: Session, document_id: int) -> dict:
    documents = {document_id: session.get(Document, document_id)}
    entities = session.exec(
        select(DocumentEntity).where(DocumentEntity.document_id == document_id)
    ).all()
    relations = session.exec(
        select(DocumentRelation).where(
            or_(
                DocumentRelation.source_document_id == document_id,
                DocumentRelation.target_document_id == document_id,
            )
        )
    ).all()
    for relation in relations:
        if relation.target_document_id:
            documents[relation.target_document_id] = session.get(
                Document, relation.target_document_id
            )

    nodes = []
    for doc_id, document in documents.items():
        if document:
            nodes.append(
                {
                    "id": f"doc:{doc_id}",
                    "type": "document",
                    "label": document.title or document.filename,
                }
            )
    for entity in entities:
        nodes.append(
            {"id": f"entity:{entity.id}", "type": entity.entity_type, "label": entity.value}
        )

    edges = []
    for entity in entities:
        edges.append(
            {"source": f"doc:{document_id}", "target": f"entity:{entity.id}", "type": "mentions"}
        )
    for relation in relations:
        if relation.target_document_id:
            edges.append(
                {
                    "source": f"doc:{relation.source_document_id}",
                    "target": f"doc:{relation.target_document_id}",
                    "type": relation.relation_type,
                }
            )
        elif relation.source_entity_id:
            edges.append(
                {
                    "source": f"doc:{relation.source_document_id}",
                    "target": f"entity:{relation.source_entity_id}",
                    "type": relation.relation_type,
                }
            )
    return {"nodes": nodes, "edges": edges}


def get_entity_graph(session: Session, entity_id: int) -> dict:
    entity = session.get(DocumentEntity, entity_id)
    if not entity:
        raise ValueError("Entity not found")
    matches = session.exec(
        select(DocumentEntity)
        .where(DocumentEntity.entity_type == entity.entity_type)
        .where(DocumentEntity.normalized_value == entity.normalized_value)
    ).all()
    nodes = [{"id": f"entity:{entity.id}", "type": entity.entity_type, "label": entity.value}]
    edges = []
    for match in matches:
        document = session.get(Document, match.document_id)
        if not document:
            continue
        nodes.append(
            {
                "id": f"doc:{document.id}",
                "type": "document",
                "label": document.title or document.filename,
            }
        )
        edges.append(
            {"source": f"doc:{document.id}", "target": f"entity:{entity.id}", "type": "mentions"}
        )
    return {"nodes": nodes, "edges": edges}


def list_relations_for_document(session: Session, document_id: int) -> list[DocumentRelation]:
    return session.exec(
        select(DocumentRelation)
        .where(
            or_(
                DocumentRelation.source_document_id == document_id,
                DocumentRelation.target_document_id == document_id,
            )
        )
        .order_by(DocumentRelation.created_at.desc())
    ).all()
