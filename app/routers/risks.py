from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from app.db.engine import get_session
from app.db.models import Document
from app.dependencies import templates
from app.schemas import DocumentRiskResponse, RiskSummaryResponse
from app.services.risk_detection_service import get_risks_summary, list_risks

router = APIRouter(tags=["risks"])


@router.get("/api/risks", response_model=list[DocumentRiskResponse])
def risks_api(
    severity: str = "",
    risk_type: str = "",
    document_id: int | None = None,
    session: Session = Depends(get_session),
):
    return list_risks(session, severity=severity, risk_type=risk_type, document_id=document_id)


@router.get("/api/risks/summary", response_model=RiskSummaryResponse)
def risks_summary_api(session: Session = Depends(get_session)):
    return get_risks_summary(session)


@router.get("/risks", name="risks_page")
def risks_page(
    request: Request,
    severity: str = "",
    risk_type: str = "",
    document_id: int | None = None,
    session: Session = Depends(get_session),
):
    return templates.TemplateResponse(
        request=request,
        name="risks.html",
        context={
            "request": request,
            "risks": list_risks(
                session, severity=severity, risk_type=risk_type, document_id=document_id
            ),
            "summary": get_risks_summary(session),
            "documents": session.exec(select(Document).order_by(Document.filename)).all(),
            "selected_severity": severity,
            "selected_risk_type": risk_type,
            "selected_document_id": document_id,
        },
    )
