from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, text
from sqlmodel import Session, select

from app.core.config import settings
from app.db.engine import engine
from app.db.models import Collection, CollectionDocumentLink, Document
from app.dependencies import templates
from app.i18n import build_language_response
from app.services.ocr import ocr_status
from app.services.processing_jobs import list_recent_processing_jobs
from app.services.processing_status import build_processing_pipeline
from app.services.runtime_settings import (
    semantic_search_configured,
    semantic_search_enabled,
    set_semantic_search_enabled,
)
from app.services.upload_report import decode_upload_report, summarize_upload_report
from app.services.vector_store import semantic_search_available

router = APIRouter()


@router.get("/health", name="health")
def health():
    with Session(engine) as session:
        session.exec(text("SELECT 1")).one()

    return {"status": "ok"}


@router.get("/language/{language}", name="set_language")
def set_language(language: str, next: str | None = None):
    return build_language_response(language, next)


@router.post("/settings/semantic-search")
def update_semantic_search(enabled: bool = Form(...)):
    if enabled and not semantic_search_configured():
        query = urlencode(
            {"semantic_error": "Semantic search needs OPENAI_API_KEY and CHROMA_DIR."}
        )
        return RedirectResponse(
            url=f"/?{query}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    set_semantic_search_enabled(enabled)
    notice = "Semantic search enabled." if enabled else "Semantic search disabled."
    query = urlencode({"semantic_notice": notice})
    return RedirectResponse(
        url=f"/?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/", name="home")
def home(
    request: Request,
    q: str | None = None,
    file_type: str | None = None,
    category: str | None = None,
    document_type: str | None = None,
    has_dates: bool | None = None,
    has_actions: bool | None = None,
    collection_id: int | None = None,
    reindexed_documents: int | None = None,
    reindexed_chunks: int | None = None,
    insights_updated: int | None = None,
    insights_skipped: int | None = None,
    upload_error: str | None = None,
    uploaded_documents: int | None = None,
    upload_report: str | None = None,
    collection_notice: str | None = None,
    collection_error: str | None = None,
    workspace_error: str | None = None,
    semantic_notice: str | None = None,
    semantic_error: str | None = None,
):
    with Session(engine) as session:
        statement = select(Document)

        if q:
            statement = statement.where(
                or_(
                    Document.filename.contains(q),
                    Document.title.contains(q),
                    Document.raw_text.contains(q),
                    Document.summary_short.contains(q),
                    Document.keywords.contains(q),
                    Document.document_type.contains(q),
                    Document.detected_dates.contains(q),
                    Document.action_items.contains(q),
                    Document.suggested_questions.contains(q),
                )
            )

        if file_type:
            statement = statement.where(Document.file_type == file_type)

        if category:
            statement = statement.where(Document.category == category)

        if document_type:
            statement = statement.where(Document.document_type == document_type)

        if has_dates:
            statement = statement.where(Document.detected_dates.is_not(None)).where(
                Document.detected_dates != ""
            )

        if has_actions:
            statement = statement.where(Document.action_items.is_not(None)).where(
                Document.action_items != ""
            )

        if collection_id:
            links = session.exec(
                select(CollectionDocumentLink).where(
                    CollectionDocumentLink.collection_id == collection_id
                )
            ).all()
            linked_document_ids = [link.document_id for link in links if link.document_id]
            if linked_document_ids:
                statement = statement.where(Document.id.in_(linked_document_ids))
            else:
                documents = []
                statement = None

        if statement is not None:
            statement = statement.order_by(Document.created_at.desc())
            documents = session.exec(statement).all()

        total_documents = session.exec(select(func.count()).select_from(Document)).one()
        total_words = session.exec(select(func.sum(Document.word_count))).one()
        total_size = session.exec(select(func.sum(Document.file_size))).one()
        avg_reading_time = session.exec(select(func.avg(Document.estimated_reading_time_min))).one()
        collections = session.exec(select(Collection).order_by(Collection.created_at.desc())).all()
        collection_links = session.exec(select(CollectionDocumentLink)).all()
        existing_document_ids = set(
            session.exec(select(Document.id).where(Document.id.is_not(None))).all()
        )
        collection_counts = {collection.id: 0 for collection in collections}
        for link in collection_links:
            if (
                link.collection_id in collection_counts
                and link.document_id in existing_document_ids
            ):
                collection_counts[link.collection_id] += 1
        collection_summaries = [
            {"collection": collection, "document_count": collection_counts.get(collection.id, 0)}
            for collection in collections
        ]
        collection_filter_options = collection_summaries
        document_types = [
            value
            for value in session.exec(
                select(Document.document_type)
                .where(Document.document_type.is_not(None))
                .where(Document.document_type != "")
                .distinct()
                .order_by(Document.document_type)
            ).all()
            if value
        ]
        processing_jobs = list_recent_processing_jobs(session, limit=8)
        has_active_processing_jobs = any(
            job.status in {"queued", "running"} for job in processing_jobs
        )

    stats = {
        "total_documents": total_documents or 0,
        "total_words": total_words or 0,
        "total_size": total_size or 0,
        "avg_reading_time": round(avg_reading_time or 0),
    }

    decoded_upload_report = summarize_upload_report(decode_upload_report(upload_report))
    legacy_upload_notice = (
        {"documents": uploaded_documents or 0} if uploaded_documents is not None else None
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "documents": documents,
            "query": q or "",
            "stats": stats,
            "selected_file_type": file_type or "",
            "selected_category": category or "",
            "selected_document_type": document_type or "",
            "selected_has_dates": bool(has_dates),
            "selected_has_actions": bool(has_actions),
            "selected_collection_id": collection_id,
            "collections": collections,
            "collection_summaries": collection_summaries,
            "collection_filter_options": collection_filter_options,
            "document_types": document_types,
            "processing_jobs": processing_jobs,
            "has_active_processing_jobs": has_active_processing_jobs,
            "document_pipeline": build_processing_pipeline,
            "current_mode": "local",
            "semantic_search_enabled": semantic_search_available(),
            "semantic_search_requested": semantic_search_enabled(),
            "semantic_search_configured": semantic_search_configured(),
            "ocr_status": ocr_status(),
            "reindex_notice": {
                "documents": reindexed_documents or 0,
                "chunks": reindexed_chunks or 0,
            }
            if reindexed_documents is not None or reindexed_chunks is not None
            else None,
            "insights_notice": {
                "updated": insights_updated or 0,
                "skipped": insights_skipped or 0,
            }
            if insights_updated is not None or insights_skipped is not None
            else None,
            "upload_error": upload_error,
            "upload_notice": legacy_upload_notice,
            "upload_report": decoded_upload_report if decoded_upload_report["total"] else None,
            "collection_notice": collection_notice,
            "collection_error": collection_error,
            "workspace_error": workspace_error,
            "semantic_notice": semantic_notice,
            "semantic_error": semantic_error,
            "upload_limits": {
                "max_file_size_mb": settings.max_file_size_mb,
                "allowed_extensions": sorted(settings.allowed_extensions_set),
            },
        },
    )
