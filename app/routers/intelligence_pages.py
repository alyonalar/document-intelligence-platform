from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
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
from app.dependencies import templates
from app.services.relationship_graph_service import rebuild_workspace_graph

router = APIRouter(tags=["intelligence-pages"])


def build_dashboard_summary(session: Session) -> dict:
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
    return {
        "total_entities": session.exec(select(func.count()).select_from(DocumentEntity)).one() or 0,
        "total_relations": session.exec(select(func.count()).select_from(DocumentRelation)).one()
        or 0,
        "open_obligations": session.exec(
            select(func.count())
            .select_from(DocumentObligation)
            .where(DocumentObligation.status == "open")
        ).one()
        or 0,
        "overdue_obligations": session.exec(
            select(func.count())
            .select_from(DocumentObligation)
            .where(DocumentObligation.status == "overdue")
        ).one()
        or 0,
        "high_risks": session.exec(
            select(func.count()).select_from(DocumentRisk).where(DocumentRisk.severity == "high")
        ).one()
        or 0,
        "documents_with_intelligence_errors": session.exec(
            select(func.count())
            .select_from(Document)
            .where(Document.intelligence_status == "error")
        ).one()
        or 0,
        "top_organizations": top_orgs,
        "top_related_documents": top_docs,
    }


@router.get("/intelligence", name="intelligence_dashboard")
def intelligence_dashboard(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request=request,
        name="intelligence.html",
        context={"request": request, "summary": build_dashboard_summary(session)},
    )


@router.get("/graph", name="graph_page")
def graph_page(request: Request, session: Session = Depends(get_session)):
    rows = session.exec(
        select(DocumentEntity, Document)
        .join(Document, Document.id == DocumentEntity.document_id)
        .order_by(DocumentEntity.entity_type, DocumentEntity.value)
        .limit(500)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="graph.html",
        context={
            "request": request,
            "rows": rows,
            "relations": session.exec(select(DocumentRelation).limit(500)).all(),
        },
    )


@router.post("/graph/rebuild", name="rebuild_graph")
def rebuild_graph(session: Session = Depends(get_session)):
    rebuild_workspace_graph(session)
    return RedirectResponse(url="/graph", status_code=status.HTTP_303_SEE_OTHER)
