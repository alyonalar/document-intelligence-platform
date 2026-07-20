import logging
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pypdf import PdfReader
from sqlmodel import Session, select

from app.core.config import settings
from app.db.engine import engine, get_session
from app.db.models import (
    Document,
    DocumentObligation,
    DocumentRelation,
    DocumentRisk,
    QAInteraction,
)
from app.dependencies import templates
from app.services.chunking import chunk_pages, chunk_text_records
from app.services.document_insights import apply_document_insights, apply_insights_to_documents
from app.services.document_lifecycle import delete_document_data, remove_stored_file
from app.services.document_structure import build_document_structure
from app.services.entity_extraction_service import get_entities_by_document
from app.services.exporter import build_document_docx, build_document_markdown, build_document_pdf
from app.services.history import list_document_interactions, save_qa_interaction
from app.services.intelligence_pipeline import process_document_intelligence
from app.services.llm import ask_llm_about_document, generate_llm_summary
from app.services.ocr import ocr_status
from app.services.parsers import parse_pdf_pages
from app.services.processing_jobs import (
    create_processing_job,
    finish_processing_job,
    list_recent_processing_jobs,
    queue_or_run_document_processing_job,
    start_processing_job,
)
from app.services.processing_status import build_processing_pipeline
from app.services.qa import answer_question
from app.services.upload_guidance import build_upload_guidance
from app.services.upload_report import encode_upload_report
from app.services.upload_validation import validate_upload_file
from app.services.vector_store import (
    reindex_document_chunks,
    semantic_search_available,
)
from app.web.responses import docx_attachment, markdown_attachment, pdf_attachment

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

PREVIEWABLE_FILE_TYPES = {"pdf", "png", "jpg", "jpeg", "tiff"}
PREVIEW_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
}
DOCUMENT_EXPORT_SECTIONS = {"metadata", "summaries", "insights", "actions", "history", "raw_text"}
PDF_THUMBNAIL_LIMIT = 6


def redirect_home(request: Request, **query_params):
    query_string = urlencode(
        {key: value for key, value in query_params.items() if value is not None}
    )
    url = str(request.url_for("home"))
    if query_string:
        url = f"{url}?{query_string}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def normalize_export_sections(sections: list[str] | None) -> set[str] | None:
    if not sections:
        return None

    normalized = {
        section.strip().lower()
        for value in sections
        for section in value.split(",")
        if section.strip()
    }
    selected = normalized & DOCUMENT_EXPORT_SECTIONS
    return selected or None


def pdf_thumbnail_backend_available() -> bool:
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        return False

    return bool(shutil.which("pdftoppm") or shutil.which("pdftocairo"))


def get_pdf_page_count(file_path: Path) -> int:
    try:
        return len(PdfReader(str(file_path)).pages)
    except Exception as e:
        logger.warning("Could not read PDF page count for %s: %s", file_path, e)
        return 0


def get_document_structure(document: Document) -> dict:
    return build_document_structure(
        document.raw_text or "",
        document.file_type,
        document.word_count,
    )


def get_document_chunks(document: Document) -> list[dict]:
    file_path = Path(document.stored_path)
    if document.file_type == "pdf" and file_path.exists():
        try:
            page_chunks = chunk_pages(parse_pdf_pages(str(file_path)), chunk_size=800, overlap=120)
            if page_chunks:
                return page_chunks
        except Exception as e:
            logger.warning("Could not build PDF chunks for document %s: %s", document.id, e)

    return chunk_text_records(document.raw_text or "", chunk_size=800, overlap=120)


def get_document_pages(document: Document) -> list[dict]:
    file_path = Path(document.stored_path)
    if document.file_type == "pdf" and file_path.exists():
        try:
            pages = parse_pdf_pages(str(file_path))
            if pages:
                return pages
        except Exception as e:
            logger.warning("Could not parse PDF pages for document %s: %s", document.id, e)

    if document.raw_text:
        return [{"page_number": 1, "text": document.raw_text}]

    return []


def build_original_preview(document: Document) -> dict | None:
    file_type = (document.file_type or "").lower()
    file_path = Path(document.stored_path)

    if file_type not in PREVIEWABLE_FILE_TYPES or not file_path.exists():
        return None

    preview = {
        "type": "image" if file_type in {"png", "jpg", "jpeg", "tiff"} else "pdf",
        "url": f"/documents/{document.id}/file",
        "filename": document.filename,
    }

    if file_type == "pdf" and pdf_thumbnail_backend_available():
        page_count = get_pdf_page_count(file_path)
        preview["thumbnails"] = [
            {
                "page_number": page_number,
                "url": f"/documents/{document.id}/thumbnail/{page_number}",
            }
            for page_number in range(1, min(page_count, PDF_THUMBNAIL_LIMIT) + 1)
        ]
        preview["total_pages"] = page_count

    return preview


def preview_snippet(text: str | None, max_length: int = 120) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def build_source_navigation(
    document_pages: list[dict],
    document_chunks: list[dict],
) -> dict:
    return {
        "pages": [
            {
                "page_number": page["page_number"],
                "snippet": preview_snippet(page.get("text")),
            }
            for page in document_pages[:12]
        ],
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "page_number": chunk.get("page_number"),
                "snippet": preview_snippet(chunk.get("text")),
            }
            for chunk in document_chunks[:16]
        ],
        "total_pages": len(document_pages),
        "total_chunks": len(document_chunks),
    }


def get_document_context(document: Document, session: Session) -> dict:
    processing_jobs = list_recent_processing_jobs(session, document.id, limit=8)
    document_chunks = get_document_chunks(document)
    document_pages = get_document_pages(document)
    document_id = document.id or 0
    return {
        "structure": get_document_structure(document),
        "document_chunks": document_chunks,
        "document_pages": document_pages,
        "original_preview": build_original_preview(document),
        "source_navigation": build_source_navigation(document_pages, document_chunks),
        "processing_pipeline": build_processing_pipeline(document),
        "processing_jobs": processing_jobs,
        "has_active_processing_jobs": any(
            job.status in {"queued", "running"} for job in processing_jobs
        ),
        "processing_guidance": build_upload_guidance(
            document.processing_error or "",
            document.processing_status,
            document.filename,
            document.file_type,
        )
        if document.processing_status in {"failed", "needs_ocr"}
        else None,
        "intelligence_entities": get_entities_by_document(session, document_id)[:50],
        "intelligence_relations": session.exec(
            select(DocumentRelation)
            .where(DocumentRelation.source_document_id == document_id)
            .limit(50)
        ).all(),
        "intelligence_obligations": session.exec(
            select(DocumentObligation)
            .where(DocumentObligation.document_id == document_id)
            .limit(50)
        ).all(),
        "intelligence_risks": session.exec(
            select(DocumentRisk).where(DocumentRisk.document_id == document_id).limit(50)
        ).all(),
    }


def build_document_template_context(
    request: Request,
    document: Document,
    session: Session,
    *,
    qa_result: dict | None = None,
    current_question: str = "",
    current_mode: str | None = None,
    reindex_result: dict | None = None,
    insights_result: dict | None = None,
) -> dict:
    history = list_document_interactions(session, document.id)
    selected_mode = current_mode or ("llm" if settings.llm_enabled else "local")
    context = {
        "request": request,
        "document": document,
        "qa_result": qa_result,
        "current_question": current_question,
        "current_mode": selected_mode,
        "llm_enabled": settings.llm_enabled,
        "semantic_search_enabled": semantic_search_available(),
        "ocr_status": ocr_status(),
        "reindex_result": reindex_result,
        "history": history,
        **get_document_context(document, session),
    }
    if insights_result is not None:
        context["insights_result"] = insights_result
    return context


def upload_result(
    filename: str,
    status: str,
    message: str,
    document_id: int | None = None,
    size: int | None = None,
    file_type: str = "",
) -> dict:
    guidance = build_upload_guidance(message, status, filename, file_type)
    return {
        "filename": filename,
        "status": status,
        "message": message,
        "document_id": document_id,
        "size": size,
        "reason": guidance["reason"],
        "suggestions": guidance["suggestions"],
    }


def build_document_history_sources(document: Document, qa_result: dict) -> list[dict]:
    raw_sources = qa_result.get("relevant_chunks") or qa_result.get("evidence") or []
    sources = []

    for index, source in enumerate(raw_sources, start=1):
        if isinstance(source, dict):
            sources.append(
                {
                    **source,
                    "document_id": document.id,
                    "filename": document.filename,
                    "chunk_id": source.get("chunk_id") or source.get("id") or index,
                    "page_number": source.get("page_number"),
                }
            )
        else:
            sources.append(
                {
                    "document_id": document.id,
                    "filename": document.filename,
                    "chunk_id": index,
                    "text": str(source),
                }
            )

    return sources


@router.get("/")
def list_documents(session: Session = Depends(get_session)):
    documents = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    return documents


@router.get("/{document_id}")
def get_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/file")
def get_document_file(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    file_type = (document.file_type or "").lower()
    if file_type not in PREVIEWABLE_FILE_TYPES:
        raise HTTPException(status_code=404, detail="Document preview is not available")

    file_path = Path(document.stored_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")

    return FileResponse(
        path=file_path,
        media_type=PREVIEW_MEDIA_TYPES.get(file_type, "application/octet-stream"),
        filename=document.filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/thumbnail/{page_number}")
def get_document_thumbnail(
    document_id: int,
    page_number: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if (document.file_type or "").lower() != "pdf":
        raise HTTPException(status_code=404, detail="PDF thumbnail is not available")

    if page_number < 1:
        raise HTTPException(status_code=404, detail="PDF page not found")

    file_path = Path(document.stored_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")

    if not pdf_thumbnail_backend_available():
        raise HTTPException(status_code=404, detail="PDF thumbnail backend is not available")

    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(
            str(file_path),
            dpi=120,
            first_page=page_number,
            last_page=page_number,
            size=(360, None),
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not render PDF thumbnail: {e}") from e

    if not pages:
        raise HTTPException(status_code=404, detail="PDF page not found")

    buffer = BytesIO()
    pages[0].save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@router.get("/{document_id}/export.md")
def export_document_markdown(
    document_id: int,
    sections: list[str] | None = Query(default=None),
):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        history = list_document_interactions(session, document_id, limit=20)
        content = build_document_markdown(
            document,
            history,
            sections=normalize_export_sections(sections),
        )

    safe_name = f"document-{document_id}.md"
    return markdown_attachment(content, safe_name)


@router.get("/{document_id}/export.docx")
def export_document_docx(
    document_id: int,
    sections: list[str] | None = Query(default=None),
):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        history = list_document_interactions(session, document_id, limit=20)
        buffer = build_document_docx(
            document,
            history,
            sections=normalize_export_sections(sections),
        )

    return docx_attachment(buffer, f"document-{document_id}.docx")


@router.get("/{document_id}/export.pdf")
def export_document_pdf(
    document_id: int,
    sections: list[str] | None = Query(default=None),
):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        history = list_document_interactions(session, document_id, limit=20)
        buffer = build_document_pdf(
            document,
            history,
            sections=normalize_export_sections(sections),
        )

    return pdf_attachment(buffer, f"document-{document_id}.pdf")


@router.get("/{document_id}/view", name="view_document")
def document_detail(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        context = build_document_template_context(request, document, session)

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=context,
    )


@router.get("/{document_id}/ask")
def ask_document(
    request: Request,
    document_id: int,
    question: str,
    mode: str = "local",
):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        if mode == "llm":
            qa_result = ask_llm_about_document(document.raw_text or "", question, document.id)
        else:
            qa_result = answer_question(document.raw_text or "", question)

        if question.strip():
            save_qa_interaction(
                session=session,
                scope="document",
                question=question,
                answer=qa_result.get("answer", ""),
                document_ids=[document_id],
                model=qa_result.get("model"),
                retrieval=qa_result.get("retrieval", "keyword" if mode == "local" else None),
                sources=build_document_history_sources(document, qa_result),
            )
            session.refresh(document)

        context = build_document_template_context(
            request,
            document,
            session,
            qa_result=qa_result,
            current_question=question,
            current_mode=mode,
        )

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=context,
    )


@router.post("/{document_id}/history/{interaction_id}/delete")
def delete_document_history_entry(
    document_id: int,
    interaction_id: int,
    session: Session = Depends(get_session),
):
    interaction = session.get(QAInteraction, interaction_id)
    if interaction and f",{document_id}," in (interaction.document_ids or ""):
        session.delete(interaction)
        session.commit()

    return RedirectResponse(
        url=f"/documents/{document_id}/view#recent-questions",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{document_id}/generate-summary")
def generate_document_summary(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        result = generate_llm_summary(document.raw_text or "")
        document.llm_summary = result["summary"]
        session.add(document)
        session.commit()

    return RedirectResponse(
        url=request.url_for("view_document", document_id=document_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{document_id}/reindex")
def reindex_document(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        job = create_processing_job(
            session, "reindex_document", document.id, "Queued document re-index."
        )
        start_processing_job(session, job, "Running document re-index.")

        document.processing_status = "indexing"
        document.processing_error = None
        session.add(document)
        session.commit()
        session.refresh(document)

        indexed_chunks = reindex_document_chunks(document)
        document.indexed_chunks = indexed_chunks
        document.processing_status = "ready" if document.raw_text else "needs_ocr"
        if not document.raw_text:
            document.processing_error = (
                "No extracted text is available. OCR is required before indexing."
            )
        session.add(document)
        session.commit()
        finish_processing_job(
            session,
            job,
            success=bool(document.raw_text),
            message=(
                f"Indexed {indexed_chunks} semantic chunk(s)."
                if document.raw_text
                else document.processing_error
            ),
        )
        session.refresh(document)
        context = build_document_template_context(
            request,
            document,
            session,
            reindex_result={
                "indexed_chunks": indexed_chunks,
                "enabled": semantic_search_available(),
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=context,
    )


@router.post("/{document_id}/recompute-insights")
def recompute_document_insights(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        insights_result = apply_document_insights(session, document)
        context = build_document_template_context(
            request,
            document,
            session,
            insights_result=insights_result,
        )

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=context,
    )


@router.post("/{document_id}/recompute-intelligence")
def recompute_document_intelligence_page(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        process_document_intelligence(session, document)
    return RedirectResponse(
        url=str(request.url_for("view_document", document_id=document_id)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{document_id}/retry")
def retry_document_processing(request: Request, document_id: int):
    with Session(engine) as session:
        document = session.get(Document, document_id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        result, job = queue_or_run_document_processing_job(
            session,
            document,
            job_type="retry_processing",
            queued_message="Queued retry processing.",
            running_message="Running retry processing.",
        )
        document = session.get(Document, document_id)
        session.refresh(document)
        indexed_chunks = result["indexed_chunks"] if result else document.indexed_chunks
        retry_success = result["success"] if result else True
        retry_message = result["message"] if result else f"Queued retry processing as job {job.id}."
        context = build_document_template_context(
            request,
            document,
            session,
            reindex_result={
                "indexed_chunks": indexed_chunks,
                "enabled": semantic_search_available(),
                "retry": True,
                "success": retry_success,
                "message": retry_message,
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="document_detail.html",
        context=context,
    )


@router.post("/reindex-all")
def reindex_all_documents(request: Request, session: Session = Depends(get_session)):
    documents = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    indexed_documents = 0
    indexed_chunks = 0

    for document in documents:
        job = create_processing_job(
            session, "reindex_document", document.id, "Queued document re-index."
        )
        start_processing_job(session, job, "Running document re-index.")

        document.processing_status = "indexing"
        document.processing_error = None
        session.add(document)
        session.commit()
        session.refresh(document)

        count = reindex_document_chunks(document)
        document.indexed_chunks = count
        document.processing_status = "ready" if document.raw_text else "needs_ocr"
        if not document.raw_text:
            document.processing_error = (
                "No extracted text is available. OCR is required before indexing."
            )
        session.add(document)
        session.commit()
        finish_processing_job(
            session,
            job,
            success=bool(document.raw_text),
            message=(
                f"Indexed {count} semantic chunk(s)."
                if document.raw_text
                else document.processing_error
            ),
        )
        if count > 0:
            indexed_documents += 1
            indexed_chunks += count

    return RedirectResponse(
        url=str(request.url_for("home"))
        + f"?reindexed_documents={indexed_documents}&reindexed_chunks={indexed_chunks}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/recompute-insights-all")
def recompute_all_document_insights(request: Request, session: Session = Depends(get_session)):
    documents = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    result = apply_insights_to_documents(session, documents)

    return RedirectResponse(
        url=str(request.url_for("home"))
        + f"?insights_updated={result['updated']}&insights_skipped={result['skipped']}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/upload")
def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
):
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    results = []

    for file in files:
        display_name = file.filename or "Unknown file"

        try:
            original_filename, extension, size = validate_upload_file(file)
        except ValueError as e:
            results.append(upload_result(display_name, "error", str(e)))
            continue

        unique_name = f"{uuid.uuid4().hex}_{original_filename}"
        destination = upload_path / unique_name

        with destination.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        document = Document(
            filename=original_filename,
            stored_path=str(destination),
            file_type=extension,
            file_size=size,
            title=original_filename,
            category="uncategorized",
            processing_status="parsing",
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        result, job = queue_or_run_document_processing_job(session, document)
        if result is None:
            results.append(
                upload_result(
                    original_filename,
                    "queued",
                    f"Uploaded and queued for processing as job {job.id}.",
                    document.id,
                    size,
                    extension,
                )
            )
            continue
        if not result["success"]:
            result_status = "needs_ocr" if result.get("status") == "needs_ocr" else "error"
            results.append(
                upload_result(
                    original_filename,
                    result_status,
                    result["message"],
                    document.id,
                    size,
                    extension,
                )
            )
            continue
        results.append(
            upload_result(
                original_filename,
                "success",
                f"Uploaded. {result['message']}",
                document.id,
                size,
                extension,
            )
        )

    return redirect_home(request, upload_report=encode_upload_report(results))


@router.post("/{document_id}/delete")
def delete_document(
    document_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = delete_document_data(session, document)
    remove_stored_file(file_path)

    return RedirectResponse(
        url=request.url_for("home"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
