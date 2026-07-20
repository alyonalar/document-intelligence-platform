from datetime import timedelta

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Document, ProcessingJob, utc_now
from app.services.document_processing import process_document
from app.services.vector_store import reindex_document_chunks


def create_processing_job(
    session: Session,
    job_type: str,
    document_id: int | None = None,
    message: str | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        job_type=job_type,
        document_id=document_id,
        message=message,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def start_processing_job(
    session: Session, job: ProcessingJob, message: str | None = None
) -> ProcessingJob:
    job.status = "running"
    job.attempts += 1
    job.started_at = utc_now()
    if message:
        job.message = message
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def finish_processing_job(
    session: Session,
    job: ProcessingJob,
    success: bool,
    message: str | None = None,
) -> ProcessingJob:
    job.status = "succeeded" if success else "failed"
    job.finished_at = utc_now()
    if message:
        job.message = message
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_recent_processing_jobs(
    session: Session,
    document_id: int | None = None,
    limit: int = 10,
) -> list[ProcessingJob]:
    statement = select(ProcessingJob)
    if document_id is not None:
        statement = statement.where(ProcessingJob.document_id == document_id)

    statement = statement.order_by(ProcessingJob.created_at.desc()).limit(limit)
    return session.exec(statement).all()


def recover_stale_running_jobs(session: Session) -> list[ProcessingJob]:
    if settings.processing_stale_minutes <= 0:
        return []

    cutoff = utc_now() - timedelta(minutes=settings.processing_stale_minutes)
    statement = (
        select(ProcessingJob)
        .where(ProcessingJob.status == "running")
        .where(ProcessingJob.started_at.is_not(None))
        .where(ProcessingJob.started_at < cutoff)
        .order_by(ProcessingJob.started_at)
    )
    jobs = session.exec(statement).all()

    for job in jobs:
        if job.attempts >= settings.processing_max_attempts:
            job.status = "failed"
            job.finished_at = utc_now()
            job.message = (
                f"Stale running job exceeded max attempts ({settings.processing_max_attempts})."
            )
        else:
            job.status = "queued"
            job.message = "Recovered stale running job and queued it for retry."
            job.started_at = None
            job.finished_at = None
        session.add(job)

    if jobs:
        session.commit()
        for job in jobs:
            session.refresh(job)

    return jobs


def run_document_processing_job(
    session: Session,
    document,
    job_type: str = "process_document",
    queued_message: str = "Queued document processing.",
    running_message: str = "Running document processing.",
) -> tuple[dict, ProcessingJob]:
    job = create_processing_job(session, job_type, document.id, queued_message)
    start_processing_job(session, job, running_message)
    result = process_document(session, document)
    finish_processing_job(session, job, success=result["success"], message=result["message"])
    return result, job


def queue_or_run_document_processing_job(
    session: Session,
    document,
    job_type: str = "process_document",
    queued_message: str = "Queued document processing.",
    running_message: str = "Running document processing.",
) -> tuple[dict | None, ProcessingJob]:
    if settings.processing_mode == "queued":
        document.processing_status = "queued"
        document.processing_error = None
        session.add(document)
        session.commit()
        session.refresh(document)
        job = create_processing_job(session, job_type, document.id, queued_message)
        return None, job

    return run_document_processing_job(
        session,
        document,
        job_type=job_type,
        queued_message=queued_message,
        running_message=running_message,
    )


def run_document_reindex_job(
    session: Session, document: Document, job: ProcessingJob
) -> ProcessingJob:
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
    session.refresh(document)

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
    return job


def run_queued_processing_job(session: Session, job: ProcessingJob) -> ProcessingJob:
    if job.status != "queued":
        return job

    if job.attempts >= settings.processing_max_attempts:
        return finish_processing_job(
            session,
            job,
            success=False,
            message=f"Max processing attempts reached ({settings.processing_max_attempts}).",
        )

    if job.document_id is None:
        start_processing_job(session, job, "Cannot run job without a document.")
        return finish_processing_job(
            session, job, success=False, message="Job is not linked to a document."
        )

    document = session.get(Document, job.document_id)
    if not document:
        start_processing_job(session, job, "Document not found.")
        return finish_processing_job(session, job, success=False, message="Document not found.")

    if job.job_type == "reindex_document":
        return run_document_reindex_job(session, document, job)

    start_processing_job(session, job, f"Running {job.job_type}.")
    result = process_document(session, document)
    finish_processing_job(session, job, success=result["success"], message=result["message"])
    return job


def get_next_queued_job(session: Session) -> ProcessingJob | None:
    recover_stale_running_jobs(session)

    statement = (
        select(ProcessingJob)
        .where(ProcessingJob.status == "queued")
        .order_by(ProcessingJob.created_at)
        .limit(1)
    )
    return session.exec(statement).first()


def process_next_queued_job(session: Session) -> ProcessingJob | None:
    job = get_next_queued_job(session)
    if not job:
        return None

    return run_queued_processing_job(session, job)
