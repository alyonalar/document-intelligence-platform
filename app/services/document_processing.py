from pathlib import Path

from sqlmodel import Session

from app.db.models import Document
from app.services.classifier import classify_document
from app.services.intelligence_pipeline import process_document_intelligence
from app.services.ocr import OCRUnavailableError, extract_text_with_ocr
from app.services.parsers import extract_text_by_extension, parse_pdf_pages
from app.services.summarizer import build_document_insights
from app.services.vector_store import delete_document_chunks, index_document_chunks

OCR_REQUIRED_MESSAGE = (
    "No readable text was extracted. This file likely needs OCR before it can be searched."
)


class OCRRequiredError(ValueError):
    pass


def extract_document_text(file_path: Path, document: Document) -> str:
    if document.file_type == "pdf":
        pages = parse_pdf_pages(str(file_path))
        if pages:
            return "\n\n".join(page["text"] for page in pages).strip()

    raw_text = extract_text_by_extension(str(file_path), document.file_type)
    if raw_text.strip():
        return raw_text

    try:
        return extract_text_with_ocr(str(file_path), document.file_type)
    except OCRUnavailableError as e:
        raise OCRRequiredError(f"{OCR_REQUIRED_MESSAGE} {str(e)}") from e


def fail_document_processing(
    session: Session,
    document: Document,
    error: str,
    status: str = "failed",
) -> dict:
    document.processing_status = status
    document.processing_error = error
    document.indexed_chunks = 0
    session.add(document)
    session.commit()
    session.refresh(document)

    return {
        "success": False,
        "message": error,
        "indexed_chunks": 0,
        "status": status,
    }


def process_document(session: Session, document: Document) -> dict:
    file_path = Path(document.stored_path)
    if not file_path.exists():
        return fail_document_processing(
            session,
            document,
            "Stored file is missing. Upload the document again before retrying.",
        )

    document.processing_status = "parsing"
    document.processing_error = None
    session.add(document)
    session.commit()
    session.refresh(document)

    try:
        raw_text = extract_document_text(file_path, document)
        insights = build_document_insights(raw_text, document.filename)
    except OCRRequiredError as e:
        return fail_document_processing(session, document, str(e), status="needs_ocr")
    except Exception as e:
        return fail_document_processing(session, document, str(e))

    category = classify_document(raw_text, document.filename)

    document.raw_text = raw_text
    document.word_count = insights["word_count"]
    document.estimated_reading_time_min = insights["estimated_reading_time_min"]
    document.summary_short = insights["summary_short"]
    document.key_points = insights["key_points"]
    document.bullet_summary = insights["bullet_summary"]
    document.keywords = insights["keywords"]
    document.document_type = insights["document_type"]
    document.detected_dates = insights["detected_dates"]
    document.action_items = insights["action_items"]
    document.suggested_questions = insights["suggested_questions"]
    document.category = category
    document.processing_status = "indexing"
    document.processing_error = None
    session.add(document)
    session.commit()
    session.refresh(document)

    if document.id is not None:
        delete_document_chunks(document.id)
    indexed_chunks = index_document_chunks(document)
    document.indexed_chunks = indexed_chunks
    document.processing_status = "ready"
    session.add(document)
    session.commit()
    session.refresh(document)

    intelligence_result = process_document_intelligence(session, document)
    session.refresh(document)

    return {
        "success": True,
        "message": f"Processed and indexed {indexed_chunks} semantic chunk(s). Intelligence: {intelligence_result['message']}",
        "indexed_chunks": indexed_chunks,
        "status": "ready",
    }
