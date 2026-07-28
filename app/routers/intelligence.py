from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.db.engine import get_session
from app.db.models import (
    Document,
    DocumentEntity,
    DocumentObligation,
    DocumentRelation,
    DocumentRisk,
)
from app.schemas import (
    BulkIntelligenceRecomputeResponse,
    DocumentEntityResponse,
    DocumentObligationResponse,
    DocumentRelationResponse,
    DocumentRiskResponse,
    GraphResponse,
    IntelligenceRecomputeResponse,
    IntelligenceSummaryResponse,
)
from app.services.entity_extraction_service import get_entities_by_document
from app.services.intelligence_pipeline import (
    process_document_intelligence,
    recompute_all_intelligence,
)
from app.services.obligation_service import list_obligations
from app.services.relationship_graph_service import get_document_graph, list_relations_for_document
from app.services.risk_detection_service import get_risks_by_document

router = APIRouter(prefix="/api", tags=["intelligence"])


@router.post(
    "/documents/{document_id}/intelligence/recompute", response_model=IntelligenceRecomputeResponse
)
def recompute_document_intelligence(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    result = process_document_intelligence(session, document)
    return IntelligenceRecomputeResponse(**result)


@router.post("/intelligence/recompute-all", response_model=BulkIntelligenceRecomputeResponse)
def recompute_all(session: Session = Depends(get_session)):
    return BulkIntelligenceRecomputeResponse(**recompute_all_intelligence(session))


@router.get("/documents/{document_id}/entities", response_model=list[DocumentEntityResponse])
def document_entities(document_id: int, session: Session = Depends(get_session)):
    return get_entities_by_document(session, document_id)


@router.get("/documents/{document_id}/relations", response_model=list[DocumentRelationResponse])
def document_relations(document_id: int, session: Session = Depends(get_session)):
    return list_relations_for_document(session, document_id)


@router.get("/documents/{document_id}/graph", response_model=GraphResponse)
def document_graph(document_id: int, session: Session = Depends(get_session)):
    return get_document_graph(session, document_id)


@router.get("/documents/{document_id}/obligations", response_model=list[DocumentObligationResponse])
def document_obligations(document_id: int, session: Session = Depends(get_session)):
    return list_obligations(session, document_id=document_id)


@router.get("/documents/{document_id}/risks", response_model=list[DocumentRiskResponse])
def document_risks(document_id: int, session: Session = Depends(get_session)):
    return get_risks_by_document(session, document_id)


@router.get("/intelligence/summary", response_model=IntelligenceSummaryResponse)
def intelligence_summary(session: Session = Depends(get_session)):
    top_orgs = session.exec(
        select(DocumentEntity.value, func.count(DocumentEntity.id))
        .where(DocumentEntity.entity_type == "organization")
        .group_by(DocumentEntity.normalized_value, DocumentEntity.value)
        .order_by(func.count(DocumentEntity.id).desc())
        .limit(10)
    ).all()
    top_docs = session.exec(
        select(Document.id, Document.filename, func.count(DocumentRelation.id))
        .join(DocumentRelation, DocumentRelation.source_document_id == Document.id)
        .group_by(Document.id, Document.filename)
        .order_by(func.count(DocumentRelation.id).desc())
        .limit(10)
    ).all()
    return IntelligenceSummaryResponse(
        total_entities=session.exec(select(func.count()).select_from(DocumentEntity)).one() or 0,
        total_relations=session.exec(select(func.count()).select_from(DocumentRelation)).one() or 0,
        open_obligations=session.exec(
            select(func.count())
            .select_from(DocumentObligation)
            .where(DocumentObligation.status == "open")
        ).one()
        or 0,
        overdue_obligations=session.exec(
            select(func.count())
            .select_from(DocumentObligation)
            .where(DocumentObligation.status == "overdue")
        ).one()
        or 0,
        high_risks=session.exec(
            select(func.count()).select_from(DocumentRisk).where(DocumentRisk.severity == "high")
        ).one()
        or 0,
        documents_with_intelligence_errors=session.exec(
            select(func.count())
            .select_from(Document)
            .where(Document.intelligence_status == "error")
        ).one()
        or 0,
        top_organizations=[{"value": value, "count": count} for value, count in top_orgs],
        top_related_documents=[
            {"document_id": doc_id, "filename": filename, "relations": count}
            for doc_id, filename, count in top_docs
        ],
    )
