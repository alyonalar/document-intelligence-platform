from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db.engine import get_session
from app.db.models import Document
from app.dependencies import templates
from app.schemas import DocumentObligationResponse, ObligationSummaryResponse
from app.services.obligation_service import (
    dismiss_obligation,
    list_obligations,
    mark_obligation_done,
    obligation_summary,
)

router = APIRouter(tags=["obligations"])


@router.get("/api/obligations", response_model=list[DocumentObligationResponse])
def obligations_api(
    status: str = "", document_id: int | None = None, session: Session = Depends(get_session)
):
    return list_obligations(session, status=status, document_id=document_id)


@router.patch("/api/obligations/{obligation_id}/status", response_model=DocumentObligationResponse)
def obligation_status_api(
    obligation_id: int, status_value: str, session: Session = Depends(get_session)
):
    try:
        if status_value == "done":
            return mark_obligation_done(session, obligation_id)
        if status_value == "dismissed":
            return dismiss_obligation(session, obligation_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    raise HTTPException(status_code=400, detail="Unsupported obligation status")


@router.get("/api/obligations/summary", response_model=ObligationSummaryResponse)
def obligations_summary_api(session: Session = Depends(get_session)):
    return obligation_summary(session)


@router.get("/obligations", name="obligations_page")
def obligations_page(
    request: Request,
    status: str = "",
    document_id: int | None = None,
    session: Session = Depends(get_session),
):
    return templates.TemplateResponse(
        request=request,
        name="obligations.html",
        context={
            "request": request,
            "obligations": list_obligations(session, status=status, document_id=document_id),
            "summary": obligation_summary(session),
            "documents": session.exec(select(Document).order_by(Document.filename)).all(),
            "selected_status": status,
            "selected_document_id": document_id,
        },
    )


@router.post("/obligations/{obligation_id}/status")
def obligation_status_page(
    obligation_id: int, status_value: str = Form(...), session: Session = Depends(get_session)
):
    if status_value == "done":
        mark_obligation_done(session, obligation_id)
    elif status_value == "dismissed":
        dismiss_obligation(session, obligation_id)
    return RedirectResponse(url="/obligations", status_code=status.HTTP_303_SEE_OTHER)
