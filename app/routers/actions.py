from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db.engine import get_session
from app.dependencies import templates
from app.services.actions import (
    action_document_types,
    list_document_actions,
    set_action_item_note,
    set_action_item_status,
    summarize_actions,
)
from app.web.responses import markdown_attachment

router = APIRouter(prefix="/actions", tags=["actions"])


STATUS_VALUES = {
    "done": "done",
    "готово": "done",
    "выполнено": "done",
    "open": "open",
    "открыто": "open",
}

COMPLETION_FILTER_VALUES = {
    **STATUS_VALUES,
    "all": "all",
    "все": "all",
    "любой статус": "all",
}

TIMING_FILTER_VALUES = {
    "overdue": "overdue",
    "просрочено": "overdue",
    "upcoming": "upcoming",
    "предстоящее": "upcoming",
    "no_date": "no_date",
    "без даты": "no_date",
}


def actions_url(request: Request, **query_params) -> str:
    query_string = urlencode(
        {key: value for key, value in query_params.items() if value not in {None, ""}}
    )
    url = str(request.url_for("actions_page"))
    if query_string:
        url = f"{url}?{query_string}"
    return url


def optional_int(value: str | int | None) -> int | None:
    if value in {None, "", "None", "null"}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalized_choice(value: str | None, choices: dict[str, str], default: str = "") -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return default
    return choices.get(cleaned.lower(), cleaned)


def build_actions_markdown(actions) -> str:
    stats = summarize_actions(actions)
    lines = [
        "# Document Actions",
        "",
        f"Total actions: {stats['total']}",
        f"Overdue: {stats['overdue']}",
        f"Upcoming: {stats['upcoming']}",
        f"Due soon: {stats['due_soon']}",
        f"No date: {stats['no_date']}",
        "",
    ]
    if not actions:
        lines.extend(["No action items found.", ""])
        return "\n".join(lines).strip() + "\n"

    for item in actions:
        lines.extend(
            [
                f"## {item.text}",
                "",
                f"- Document: {item.title}",
                f"- Filename: {item.filename}",
                f"- Type: {item.document_type}",
                f"- Source: /documents/{item.document_id}/view{item.source_anchor}",
                f"- Timing: {item.due_label}",
                f"- Due date source: {item.due_date_source}",
                f"- Status: {item.completion_status}",
            ]
        )
        if item.note:
            lines.append(f"- Note: {item.note}")
        if item.dates:
            lines.append(f"- Dates: {', '.join(item.dates)}")
        if item.context:
            lines.extend(["", "Context:", "", f"> {item.context}", ""])
        lines.append("")

    return "\n".join(lines).strip() + "\n"


@router.get("", name="actions_page")
def actions_page(
    request: Request,
    q: str = "",
    document_type: str = "",
    document_id: int | None = None,
    has_dates: bool = False,
    timing_status: str = "",
    completion_status: str = "open",
    session: Session = Depends(get_session),
):
    timing_status = normalized_choice(timing_status, TIMING_FILTER_VALUES)
    completion_status = normalized_choice(completion_status, COMPLETION_FILTER_VALUES, "open")
    actions = list_document_actions(
        session,
        query=q,
        document_type=document_type,
        document_id=document_id,
        has_dates=has_dates,
        timing_status=timing_status,
        completion_status=completion_status,
        limit=300,
    )

    return templates.TemplateResponse(
        request=request,
        name="actions.html",
        context={
            "request": request,
            "actions": actions,
            "action_stats": summarize_actions(actions),
            "query": q,
            "selected_document_type": document_type,
            "selected_document_id": document_id,
            "selected_has_dates": has_dates,
            "selected_timing_status": timing_status,
            "selected_completion_status": completion_status,
            "document_types": action_document_types(session),
        },
    )


@router.get("/export.md")
def export_actions_markdown(
    q: str = "",
    document_type: str = "",
    document_id: int | None = None,
    has_dates: bool = False,
    timing_status: str = "",
    completion_status: str = "open",
    session: Session = Depends(get_session),
):
    timing_status = normalized_choice(timing_status, TIMING_FILTER_VALUES)
    completion_status = normalized_choice(completion_status, COMPLETION_FILTER_VALUES, "open")
    actions = list_document_actions(
        session,
        query=q,
        document_type=document_type,
        document_id=document_id,
        has_dates=has_dates,
        timing_status=timing_status,
        completion_status=completion_status,
        limit=1000,
    )
    return markdown_attachment(build_actions_markdown(actions), "document-actions.md")


@router.post("/{action_key}/status")
def update_action_status(
    request: Request,
    action_key: str,
    status_value: str = Form(...),
    q: str = Form(""),
    document_type: str = Form(""),
    document_id: str = Form(""),
    has_dates: bool = Form(False),
    timing_status: str = Form(""),
    completion_status: str = Form("open"),
    session: Session = Depends(get_session),
):
    status_value = normalized_choice(status_value, STATUS_VALUES)
    timing_status = normalized_choice(timing_status, TIMING_FILTER_VALUES)
    completion_status = normalized_choice(completion_status, COMPLETION_FILTER_VALUES, "open")
    set_action_item_status(session, action_key, status_value)
    next_completion_status = completion_status
    if (status_value == "done" and completion_status == "open") or (
        status_value == "open" and completion_status == "done"
    ):
        next_completion_status = "all"
    return RedirectResponse(
        url=actions_url(
            request,
            q=q,
            document_type=document_type,
            document_id=optional_int(document_id),
            has_dates="true" if has_dates else "",
            timing_status=timing_status,
            completion_status=next_completion_status,
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{action_key}/note")
def update_action_note(
    request: Request,
    action_key: str,
    note: str = Form(""),
    due_date_override: str = Form(""),
    q: str = Form(""),
    document_type: str = Form(""),
    document_id: str = Form(""),
    has_dates: bool = Form(False),
    timing_status: str = Form(""),
    completion_status: str = Form("open"),
    session: Session = Depends(get_session),
):
    timing_status = normalized_choice(timing_status, TIMING_FILTER_VALUES)
    completion_status = normalized_choice(completion_status, COMPLETION_FILTER_VALUES, "open")
    set_action_item_note(session, action_key, note, due_date_override)
    return RedirectResponse(
        url=actions_url(
            request,
            q=q,
            document_type=document_type,
            document_id=optional_int(document_id),
            has_dates="true" if has_dates else "",
            timing_status=timing_status,
            completion_status=completion_status,
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
