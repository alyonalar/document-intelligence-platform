from sqlmodel import Session

from app.db.models import Document
from app.services.summarizer import build_document_insights


def apply_document_insights(session: Session, document: Document) -> dict:
    if not document.raw_text:
        return {
            "success": False,
            "message": "No extracted text is available for insights.",
            "document_type": document.document_type or "general document",
            "dates": 0,
            "actions": 0,
            "questions": 0,
        }

    insights = build_document_insights(document.raw_text, document.filename)
    document.document_type = insights["document_type"]
    document.detected_dates = insights["detected_dates"]
    document.action_items = insights["action_items"]
    document.suggested_questions = insights["suggested_questions"]
    session.add(document)
    session.commit()
    session.refresh(document)

    dates = [line for line in (document.detected_dates or "").splitlines() if line.strip()]
    actions = [line for line in (document.action_items or "").splitlines() if line.strip()]
    questions = [line for line in (document.suggested_questions or "").splitlines() if line.strip()]

    return {
        "success": True,
        "message": "Document insights updated.",
        "document_type": document.document_type or "general document",
        "dates": len(dates),
        "actions": len(actions),
        "questions": len(questions),
    }


def apply_insights_to_documents(session: Session, documents: list[Document]) -> dict:
    updated = 0
    skipped = 0

    for document in documents:
        result = apply_document_insights(session, document)
        if result["success"]:
            updated += 1
        else:
            skipped += 1

    return {
        "updated": updated,
        "skipped": skipped,
        "total": len(documents),
    }
