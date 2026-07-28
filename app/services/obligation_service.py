import re
from datetime import timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from app.db.models import Document, DocumentObligation, utc_now
from app.services.intelligence_utils import first_date_in_text, infer_amount, split_sentences

OBLIGATION_RE = re.compile(
    r"\b(должен|должна|обязуется|необходимо|не позднее|в течение \d+ дней|оплатить|предоставить|направить|подписать|передать|выполнить|deliver|pay|provide|submit|no later than|within \d+ days)\b",
    flags=re.IGNORECASE,
)
ACTION_RE = re.compile(
    r"\b(оплатить|предоставить|направить|подписать|передать|выполнить|deliver|pay|provide|submit)\b",
    re.IGNORECASE,
)


def _infer_subject(sentence: str) -> str:
    words = sentence.split()
    if not words:
        return "Unspecified party"
    return " ".join(words[: min(4, len(words))]).strip(" ,.;:") or "Unspecified party"


def _infer_action(sentence: str) -> str:
    match = ACTION_RE.search(sentence)
    if match:
        return match.group(0).lower()
    return "perform obligation"


def _status_for_due_date(due_date) -> str:
    if not due_date:
        return "no_due_date"
    return "overdue" if due_date.date() < utc_now().date() else "open"


def _rule_score(*, action: str, due_date, amount: float | None) -> float:
    score = 0.58
    if action != "perform obligation":
        score += 0.12
    if due_date is not None:
        score += 0.12
    if amount is not None:
        score += 0.08
    return min(score, 0.9)


def extract_obligations(
    session: Session,
    document_id: int,
    *,
    commit: bool = True,
) -> list[DocumentObligation]:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")

    session.exec(delete(DocumentObligation).where(DocumentObligation.document_id == document_id))
    obligations = []
    for index, sentence in enumerate(split_sentences(document.raw_text or ""), start=1):
        if not OBLIGATION_RE.search(sentence):
            continue
        due_text, due_date = first_date_in_text(sentence)
        relative_due = re.search(
            r"(?:в течение|within)\s+(\d+)\s+(?:дней|days)", sentence, re.IGNORECASE
        )
        if relative_due and due_date is None:
            due_text = relative_due.group(0)
            due_date = utc_now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=int(relative_due.group(1))
            )
        amount, currency = infer_amount(sentence)
        action = _infer_action(sentence)
        obligation = DocumentObligation(
            document_id=document_id,
            subject=_infer_subject(sentence),
            action=action,
            object=sentence[:180],
            due_date=due_date,
            due_date_text=due_text,
            amount=amount,
            currency=currency,
            status=_status_for_due_date(due_date),
            source_text=sentence,
            chunk_index=index,
            confidence=_rule_score(action=action, due_date=due_date, amount=amount),
        )
        session.add(obligation)
        obligations.append(obligation)
    if commit:
        session.commit()
    else:
        session.flush()
    for obligation in obligations:
        session.refresh(obligation)
    return obligations


def update_obligation_statuses(session: Session) -> list[DocumentObligation]:
    obligations = session.exec(select(DocumentObligation)).all()
    for obligation in obligations:
        if obligation.status in {"done", "dismissed"}:
            continue
        obligation.status = _status_for_due_date(obligation.due_date)
        obligation.updated_at = utc_now()
        session.add(obligation)
    session.commit()
    return obligations


def mark_obligation_done(session: Session, obligation_id: int) -> DocumentObligation:
    obligation = session.get(DocumentObligation, obligation_id)
    if not obligation:
        raise ValueError("Obligation not found")
    obligation.status = "done"
    obligation.updated_at = utc_now()
    session.add(obligation)
    session.commit()
    session.refresh(obligation)
    return obligation


def dismiss_obligation(session: Session, obligation_id: int) -> DocumentObligation:
    obligation = session.get(DocumentObligation, obligation_id)
    if not obligation:
        raise ValueError("Obligation not found")
    obligation.status = "dismissed"
    obligation.updated_at = utc_now()
    session.add(obligation)
    session.commit()
    session.refresh(obligation)
    return obligation


def list_obligations(
    session: Session, status: str = "", document_id: int | None = None
) -> list[DocumentObligation]:
    update_obligation_statuses(session)
    statement = select(DocumentObligation)
    if status:
        statement = statement.where(DocumentObligation.status == status)
    if document_id is not None:
        statement = statement.where(DocumentObligation.document_id == document_id)
    return session.exec(
        statement.order_by(DocumentObligation.due_date, DocumentObligation.created_at.desc())
    ).all()


def obligation_summary(session: Session) -> dict:
    obligations = list_obligations(session)
    today = utc_now().date()
    due_soon = [
        item
        for item in obligations
        if item.due_date
        and 0 <= (item.due_date.date() - today).days <= 14
        and item.status == "open"
    ]
    return {
        "total": len(obligations),
        "open": sum(1 for item in obligations if item.status == "open"),
        "overdue": sum(1 for item in obligations if item.status == "overdue"),
        "due_soon": len(due_soon),
        "no_due_date": sum(1 for item in obligations if item.status == "no_due_date"),
        "done": sum(1 for item in obligations if item.status == "done"),
        "dismissed": sum(1 for item in obligations if item.status == "dismissed"),
    }
