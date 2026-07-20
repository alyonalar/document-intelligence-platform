import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session, select

from app.db.models import ActionItemState, Document, utc_now
from app.services.chunking import chunk_text_records


@dataclass
class DocumentActionItem:
    id: str
    action_key: str
    text: str
    document_id: int
    filename: str
    title: str
    document_type: str
    dates: list[str]
    due_date: str | None
    due_date_override: str | None
    due_date_source: str
    due_label: str
    timing_status: str
    days_until: int | None
    context: str
    completed: bool
    completion_status: str
    note: str
    source_chunk_id: int | None
    source_anchor: str
    created_at: str


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
    "\u044f\u043d\u0432\u0430\u0440\u044f": 1,
    "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2,
    "\u043c\u0430\u0440\u0442\u0430": 3,
    "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
    "\u043c\u0430\u044f": 5,
    "\u0438\u044e\u043d\u044f": 6,
    "\u0438\u044e\u043b\u044f": 7,
    "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
    "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9,
    "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10,
    "\u043d\u043e\u044f\u0431\u0440\u044f": 11,
    "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
}


def split_lines(value: str | None) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def action_context(text: str | None, action_text: str, window: int = 180) -> str:
    normalized_text = normalize_space(text or "")
    normalized_action = normalize_space(action_text)
    if not normalized_action:
        return ""

    index = normalized_text.lower().find(normalized_action.lower())
    if index == -1:
        return normalized_action

    start = max(0, index - window)
    end = min(len(normalized_text), index + len(normalized_action) + window)
    snippet = normalized_text[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(normalized_text):
        snippet = f"{snippet}..."
    return snippet


def action_key(document_id: int, text: str) -> str:
    payload = f"{document_id}:{normalize_space(text).lower()}".encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def action_source_anchor(raw_text: str | None, action_text: str) -> tuple[int | None, str]:
    normalized_action = normalize_space(action_text).lower()
    if not normalized_action:
        return None, "#extracted-text"

    for chunk in chunk_text_records(raw_text or "", chunk_size=800, overlap=120):
        if normalized_action in normalize_space(chunk["text"]).lower():
            chunk_id = chunk["chunk_id"]
            return chunk_id, f"#chunk-{chunk_id}"

    return None, "#extracted-text"


def parse_date_value(value: str) -> date | None:
    value = value.strip().replace(",", "")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    month_match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})", value)
    if month_match:
        month_name, day, year = month_match.groups()
        month = MONTHS.get(month_name.lower())
        if month:
            return date(int(year), month, int(day))

    russian_match = re.fullmatch(
        r"(\d{1,2})\s+([\u0410-\u042f\u0430-\u044f\u0451\u0401]+)\s+(\d{4})",
        value,
    )
    if russian_match:
        day, month_name, year = russian_match.groups()
        month = MONTHS.get(month_name.lower())
        if month:
            return date(int(year), month, int(day))

    return None


def nearest_due_date(values: list[str]) -> date | None:
    parsed = [parsed for value in values if (parsed := parse_date_value(value))]
    if not parsed:
        return None
    return min(parsed)


def timing_for_due_date(
    due_date: date | None, today: date | None = None
) -> tuple[str, int | None, str]:
    if due_date is None:
        return "no_date", None, "No date"

    today = today or date.today()
    days_until = (due_date - today).days
    if days_until < 0:
        return "overdue", days_until, f"{abs(days_until)} day(s) overdue"
    if days_until == 0:
        return "upcoming", days_until, "Due today"
    return "upcoming", days_until, f"Due in {days_until} day(s)"


def document_to_action_items(
    document: Document,
    states: dict[str, ActionItemState] | None = None,
) -> list[DocumentActionItem]:
    if document.id is None:
        return []

    states = states or {}
    dates = split_lines(document.detected_dates)
    items = []
    for index, text in enumerate(split_lines(document.action_items), start=1):
        key = action_key(document.id, text)
        state = states.get(key)
        completed = state is not None and state.status == "done"
        manual_due = (
            parse_date_value(state.due_date_override) if state and state.due_date_override else None
        )
        extracted_due = nearest_due_date(dates)
        due = manual_due or extracted_due
        due_source = "manual" if manual_due else "extracted" if extracted_due else "none"
        timing_status, days_until, due_label = timing_for_due_date(due)
        source_chunk_id, source_anchor = action_source_anchor(document.raw_text, text)
        items.append(
            DocumentActionItem(
                id=f"{document.id}-{index}",
                action_key=key,
                text=text,
                document_id=document.id,
                filename=document.filename,
                title=document.title or document.filename,
                document_type=document.document_type or "general document",
                dates=dates,
                due_date=due.isoformat() if due else None,
                due_date_override=state.due_date_override
                if state and state.due_date_override
                else None,
                due_date_source=due_source,
                due_label=due_label,
                timing_status=timing_status,
                days_until=days_until,
                context=action_context(document.raw_text, text),
                completed=completed,
                completion_status="done" if completed else "open",
                note=state.note if state and state.note else "",
                source_chunk_id=source_chunk_id,
                source_anchor=source_anchor,
                created_at=document.created_at.isoformat(),
            )
        )
    return items


def summarize_actions(actions: list[DocumentActionItem]) -> dict:
    due_soon = sum(
        1 for item in actions if item.days_until is not None and 0 <= item.days_until <= 7
    )
    return {
        "total": len(actions),
        "overdue": sum(1 for item in actions if item.timing_status == "overdue"),
        "upcoming": sum(1 for item in actions if item.timing_status == "upcoming"),
        "no_date": sum(1 for item in actions if item.timing_status == "no_date"),
        "due_soon": due_soon,
        "done": sum(1 for item in actions if item.completed),
        "open": sum(1 for item in actions if not item.completed),
    }


def list_document_actions(
    session: Session,
    query: str = "",
    document_type: str = "",
    document_id: int | None = None,
    has_dates: bool = False,
    timing_status: str = "",
    completion_status: str = "open",
    limit: int = 200,
) -> list[DocumentActionItem]:
    statement = (
        select(Document)
        .where(Document.action_items.is_not(None))
        .where(Document.action_items != "")
        .order_by(Document.created_at.desc())
    )

    if document_id is not None:
        statement = statement.where(Document.id == document_id)

    if document_type.strip():
        statement = statement.where(Document.document_type == document_type.strip())

    if has_dates:
        statement = statement.where(Document.detected_dates.is_not(None)).where(
            Document.detected_dates != ""
        )

    documents = session.exec(statement).all()
    states = {state.action_key: state for state in session.exec(select(ActionItemState)).all()}
    normalized_query = query.strip().lower()
    actions = []

    for document in documents:
        for item in document_to_action_items(document, states):
            searchable = " ".join(
                [
                    item.text,
                    item.filename,
                    item.title,
                    item.document_type,
                    " ".join(item.dates),
                    item.context,
                    item.note,
                ]
            ).lower()
            if normalized_query and normalized_query not in searchable:
                continue
            if timing_status.strip() and item.timing_status != timing_status.strip():
                continue
            if completion_status == "open" and item.completed:
                continue
            if completion_status == "done" and not item.completed:
                continue
            actions.append(item)

    actions.sort(
        key=lambda item: (
            item.due_date is None,
            item.due_date or "9999-12-31",
            item.created_at,
        )
    )
    return actions[:limit]


def set_action_item_status(session: Session, key: str, status: str) -> ActionItemState:
    if status not in {"done", "open"}:
        raise ValueError("Action status must be 'done' or 'open'")

    existing = session.exec(
        select(ActionItemState).where(ActionItemState.action_key == key)
    ).first()

    if status == "open":
        if existing:
            session.delete(existing)
            session.commit()
            return ActionItemState(action_key=key, status="open")
        return ActionItemState(action_key=key, status="open")

    if existing:
        existing.status = "done"
        existing.updated_at = utc_now()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    state = ActionItemState(action_key=key, status="done")
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def set_action_item_note(
    session: Session,
    key: str,
    note: str,
    due_date_override: str | None = None,
) -> ActionItemState:
    cleaned_note = note.strip()
    cleaned_due_date = (due_date_override or "").strip()
    if cleaned_due_date and parse_date_value(cleaned_due_date) is None:
        raise ValueError("Due date override must be a supported date value")

    existing = session.exec(
        select(ActionItemState).where(ActionItemState.action_key == key)
    ).first()

    if existing:
        existing.note = cleaned_note or None
        existing.due_date_override = cleaned_due_date or None
        existing.updated_at = utc_now()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    state = ActionItemState(
        action_key=key,
        status="open",
        note=cleaned_note or None,
        due_date_override=cleaned_due_date or None,
    )
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def action_document_types(session: Session) -> list[str]:
    values = session.exec(
        select(Document.document_type)
        .where(Document.action_items.is_not(None))
        .where(Document.action_items != "")
        .where(Document.document_type.is_not(None))
        .where(Document.document_type != "")
        .distinct()
        .order_by(Document.document_type)
    ).all()
    return [value for value in values if value]
