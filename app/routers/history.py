from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlmodel import Session

from app.db.engine import get_session
from app.db.models import QAInteraction
from app.dependencies import templates
from app.services.exporter import build_history_markdown
from app.services.history import attach_sources, search_interactions

router = APIRouter(prefix="/history", tags=["history"])


def history_url(request: Request, **query_params) -> str:
    query_string = urlencode({key: value for key, value in query_params.items() if value})
    url = str(request.url_for("history_page"))
    if query_string:
        url = f"{url}?{query_string}"
    return url


def markdown_attachment(content: str, filename: str) -> PlainTextResponse:
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", name="history_page")
def history_page(
    request: Request,
    q: str = "",
    scope: str = "",
    deleted: int = 0,
    session: Session = Depends(get_session),
):
    interactions = search_interactions(session, query=q, scope=scope, limit=100)

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "request": request,
            "interactions": attach_sources(interactions),
            "query": q,
            "scope": scope,
            "deleted": deleted,
        },
    )


@router.get("/export.md")
def export_history_markdown(
    q: str = "",
    scope: str = "",
    session: Session = Depends(get_session),
):
    interactions = search_interactions(session, query=q, scope=scope, limit=500)
    content = build_history_markdown(interactions)
    return markdown_attachment(content, "question-history.md")


@router.post("/{interaction_id}/delete")
def delete_history_entry(
    request: Request,
    interaction_id: int,
    q: str = Form(""),
    scope: str = Form(""),
    session: Session = Depends(get_session),
):
    interaction = session.get(QAInteraction, interaction_id)
    if interaction:
        session.delete(interaction)
        session.commit()

    return RedirectResponse(
        url=history_url(request, q=q, scope=scope, deleted=1),
        status_code=status.HTTP_303_SEE_OTHER,
    )
