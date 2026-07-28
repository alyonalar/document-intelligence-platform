from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.engine import get_session
from app.db.models import Document, ProcessingJob
from app.schemas import (
    ActionItemResponse,
    ActionListResponse,
    ActionNoteUpdateResponse,
    ActionStatsResponse,
    ActionStatusUpdateResponse,
    AskDocumentRequest,
    AskResponse,
    AskWorkspaceRequest,
    BulkDocumentInsightsResponse,
    CompareDocumentsRequest,
    CompareDocumentsResponse,
    DocumentDetailResponse,
    DocumentInsightsResponse,
    DocumentListItem,
    DocumentSearchResponse,
    DocumentStructure,
    ProcessingJobItem,
    ProcessingJobListResponse,
    SourceItem,
)
from app.services.actions import (
    list_document_actions,
    set_action_item_note,
    set_action_item_status,
    summarize_actions,
)
from app.services.document_compare import compare_documents
from app.services.document_diff import build_document_diff
from app.services.document_insights import apply_document_insights, apply_insights_to_documents
from app.services.document_structure import build_document_structure
from app.services.llm import ask_llm_about_document
from app.services.multi_doc_qa import ask_llm_across_documents
from app.services.processing_jobs import queue_or_run_document_processing_job
from app.services.processing_status import build_processing_pipeline
from app.services.qa import answer_question

router = APIRouter(prefix="/api", tags=["api"])


def document_to_list_item(document: Document) -> DocumentListItem:
    pipeline = build_processing_pipeline(document)
    return DocumentListItem(
        id=document.id or 0,
        filename=document.filename,
        file_type=document.file_type,
        file_size=document.file_size,
        word_count=document.word_count,
        estimated_reading_time_min=document.estimated_reading_time_min,
        category=document.category,
        summary_short=document.summary_short,
        keywords=document.keywords,
        document_type=document.document_type,
        detected_dates=document.detected_dates,
        action_items=document.action_items,
        suggested_questions=document.suggested_questions,
        processing_status=document.processing_status,
        processing_label=pipeline["label"],
        processing_progress=pipeline["progress"],
        processing_error=document.processing_error,
        indexed_chunks=document.indexed_chunks,
    )


def normalize_sources(raw_sources) -> list[SourceItem | str]:
    sources = []
    for source in raw_sources or []:
        if isinstance(source, str):
            sources.append(source)
            continue

        if isinstance(source, dict):
            sources.append(
                SourceItem(
                    document_id=source.get("document_id"),
                    filename=source.get("filename"),
                    chunk_id=source.get("chunk_id") or source.get("id"),
                    page_number=source.get("page_number"),
                    text=source.get("text", ""),
                    score=source.get("score"),
                )
            )
    return sources


def job_to_item(job: ProcessingJob) -> ProcessingJobItem:
    return ProcessingJobItem(
        id=job.id or 0,
        job_type=job.job_type,
        status=job.status,
        document_id=job.document_id,
        message=job.message,
        attempts=job.attempts,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def action_to_item(item) -> ActionItemResponse:
    return ActionItemResponse(
        id=item.id,
        text=item.text,
        document_id=item.document_id,
        filename=item.filename,
        title=item.title,
        document_type=item.document_type,
        dates=item.dates,
        due_date=item.due_date,
        due_date_override=item.due_date_override,
        due_date_source=item.due_date_source,
        due_label=item.due_label,
        timing_status=item.timing_status,
        days_until=item.days_until,
        context=item.context,
        action_key=item.action_key,
        completed=item.completed,
        completion_status=item.completion_status,
        note=item.note,
        source_chunk_id=item.source_chunk_id,
        source_anchor=item.source_anchor,
        created_at=item.created_at,
    )


@router.get("/actions", response_model=ActionListResponse)
def list_actions_api(
    q: str = "",
    document_type: str = "",
    document_id: int | None = None,
    has_dates: bool = False,
    timing_status: str = "",
    completion_status: str = "open",
    limit: int = 200,
    session: Session = Depends(get_session),
):
    actions = list_document_actions(
        session,
        query=q,
        document_type=document_type,
        document_id=document_id,
        has_dates=has_dates,
        timing_status=timing_status,
        completion_status=completion_status,
        limit=limit,
    )
    return ActionListResponse(
        query=q,
        total=len(actions),
        stats=ActionStatsResponse(**summarize_actions(actions)),
        actions=[action_to_item(item) for item in actions],
    )


@router.post("/actions/{action_key}/status", response_model=ActionStatusUpdateResponse)
def update_action_status_api(
    action_key: str, status_value: str, session: Session = Depends(get_session)
):
    try:
        state = set_action_item_status(session, action_key, status_value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ActionStatusUpdateResponse(
        action_key=action_key,
        status=status_value,
        stored_status=state.status,
    )


@router.post("/actions/{action_key}/note", response_model=ActionNoteUpdateResponse)
def update_action_note_api(
    action_key: str,
    note: str = "",
    due_date_override: str = "",
    session: Session = Depends(get_session),
):
    try:
        state = set_action_item_note(session, action_key, note, due_date_override)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ActionNoteUpdateResponse(
        action_key=action_key,
        note=state.note or "",
        due_date_override=state.due_date_override,
        status=state.status,
    )


@router.get("/documents/search", response_model=DocumentSearchResponse)
def search_documents(
    q: str = "",
    file_type: str = "",
    category: str = "",
    document_type: str = "",
    has_dates: bool = False,
    has_actions: bool = False,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    statement = select(Document)

    if q.strip():
        query = q.strip()
        statement = statement.where(
            or_(
                Document.filename.contains(query),
                Document.title.contains(query),
                Document.raw_text.contains(query),
                Document.summary_short.contains(query),
                Document.keywords.contains(query),
                Document.document_type.contains(query),
                Document.detected_dates.contains(query),
                Document.action_items.contains(query),
                Document.suggested_questions.contains(query),
            )
        )

    if file_type.strip():
        statement = statement.where(Document.file_type == file_type.strip())

    if category.strip():
        statement = statement.where(Document.category == category.strip())

    if document_type.strip():
        statement = statement.where(Document.document_type == document_type.strip())

    if has_dates:
        statement = statement.where(Document.detected_dates.is_not(None)).where(
            Document.detected_dates != ""
        )

    if has_actions:
        statement = statement.where(Document.action_items.is_not(None)).where(
            Document.action_items != ""
        )

    statement = statement.order_by(Document.created_at.desc()).limit(limit)
    documents = session.exec(statement).all()

    return DocumentSearchResponse(
        query=q,
        total=len(documents),
        documents=[document_to_list_item(document) for document in documents],
    )


@router.get("/jobs", response_model=ProcessingJobListResponse)
def list_jobs_api(
    status: str = "",
    document_id: int | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    statement = select(ProcessingJob)

    if status.strip():
        statement = statement.where(ProcessingJob.status == status.strip())

    if document_id is not None:
        statement = statement.where(ProcessingJob.document_id == document_id)

    statement = statement.order_by(ProcessingJob.created_at.desc()).limit(limit)
    jobs = session.exec(statement).all()

    return ProcessingJobListResponse(
        total=len(jobs),
        jobs=[job_to_item(job) for job in jobs],
    )


@router.get("/jobs/{job_id}", response_model=ProcessingJobItem)
def get_job_api(job_id: int, session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found")

    return job_to_item(job)


@router.get("/documents/{document_id}/jobs", response_model=ProcessingJobListResponse)
def list_document_jobs_api(
    document_id: int,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    statement = (
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(limit)
    )
    jobs = session.exec(statement).all()

    return ProcessingJobListResponse(
        total=len(jobs),
        jobs=[job_to_item(job) for job in jobs],
    )


@router.post("/documents/{document_id}/process", response_model=ProcessingJobItem)
def process_document_api(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    _, job = queue_or_run_document_processing_job(
        session,
        document,
        job_type="api_process_document",
        queued_message="Queued API document processing.",
        running_message="Running API document processing.",
    )

    return job_to_item(job)


@router.post("/jobs/{job_id}/retry", response_model=ProcessingJobItem)
def retry_job_api(job_id: int, session: Session = Depends(get_session)):
    job = session.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Processing job not found")

    if job.document_id is None:
        raise HTTPException(status_code=400, detail="Only document jobs can be retried")

    document = session.get(Document, job.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    _, retry_job = queue_or_run_document_processing_job(
        session,
        document,
        job_type=f"retry_{job.job_type}",
        queued_message=f"Queued retry for job {job.id}.",
        running_message=f"Running retry for job {job.id}.",
    )

    return job_to_item(retry_job)


@router.post("/documents/{document_id}/insights", response_model=DocumentInsightsResponse)
def recompute_document_insights_api(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentInsightsResponse(**apply_document_insights(session, document))


@router.post("/documents/insights/recompute", response_model=BulkDocumentInsightsResponse)
def recompute_all_document_insights_api(session: Session = Depends(get_session)):
    documents = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    return BulkDocumentInsightsResponse(**apply_insights_to_documents(session, documents))


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail_api(
    document_id: int,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    structure = build_document_structure(
        document.raw_text or "",
        document.file_type,
        document.word_count,
    )

    return DocumentDetailResponse(
        **document_to_list_item(document).model_dump(),
        raw_text=document.raw_text,
        llm_summary=document.llm_summary,
        structure=DocumentStructure(**structure),
    )


@router.post("/documents/{document_id}/ask", response_model=AskResponse)
def ask_document_api(
    document_id: int,
    payload: AskDocumentRequest,
    session: Session = Depends(get_session),
):
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.mode == "llm":
        result = ask_llm_about_document(document.raw_text or "", payload.question, document.id)
    else:
        result = answer_question(document.raw_text or "", payload.question)

    return AskResponse(
        question=payload.question,
        answer=result.get("answer", ""),
        model=result.get("model"),
        retrieval=result.get("retrieval", "keyword" if payload.mode == "local" else None),
        sources=normalize_sources(result.get("relevant_chunks") or result.get("evidence") or []),
    )


@router.post("/workspace/ask", response_model=AskResponse)
def ask_workspace_api(
    payload: AskWorkspaceRequest,
    session: Session = Depends(get_session),
):
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="document_ids is required")

    documents = []
    for document_id in payload.document_ids:
        document = session.get(Document, document_id)
        if document:
            documents.append(document)

    if not documents:
        raise HTTPException(status_code=404, detail="No matching documents found")

    result = ask_llm_across_documents(documents, payload.question)

    return AskResponse(
        question=payload.question,
        answer=result.get("answer", ""),
        model=result.get("model"),
        retrieval="semantic_or_keyword",
        sources=normalize_sources(result.get("sources")),
    )


@router.post("/documents/compare", response_model=CompareDocumentsResponse)
def compare_documents_api(
    payload: CompareDocumentsRequest,
    session: Session = Depends(get_session),
):
    documents = [session.get(Document, document_id) for document_id in payload.document_ids]
    documents = [document for document in documents if document]

    if len(documents) != 2:
        raise HTTPException(status_code=404, detail="Two matching documents are required")

    diff = build_document_diff(
        doc1_name=documents[0].filename,
        doc1_text=documents[0].raw_text or "",
        doc2_name=documents[1].filename,
        doc2_text=documents[1].raw_text or "",
    )
    llm_result = compare_documents(
        doc1_name=documents[0].filename,
        doc1_text=documents[0].raw_text or "",
        doc2_name=documents[1].filename,
        doc2_text=documents[1].raw_text or "",
    )

    return CompareDocumentsResponse(
        diff=diff,
        llm_answer=llm_result.get("answer"),
        model=llm_result.get("model"),
    )
