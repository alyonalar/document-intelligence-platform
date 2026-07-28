from datetime import timedelta

from sqlmodel import Session

from app.core.config import settings
from app.db.engine import engine
from app.db.models import Document, ProcessingJob, utc_now
from app.services.processing_jobs import (
    create_processing_job,
    finish_processing_job,
    list_recent_processing_jobs,
    process_next_queued_job,
    recover_stale_running_jobs,
    start_processing_job,
)


def test_processing_job_lifecycle():
    with Session(engine) as session:
        job = create_processing_job(session, "unit_test", document_id=None, message="Queued")

        assert job.status == "queued"

        job = start_processing_job(session, job, "Running")
        assert job.status == "running"
        assert job.attempts == 1
        assert job.started_at is not None

        job = finish_processing_job(session, job, success=True, message="Done")
        assert job.status == "succeeded"
        assert job.finished_at is not None

        jobs = list_recent_processing_jobs(session, limit=1)
        assert jobs[0].id == job.id


def test_process_next_queued_job_processes_document(tmp_path):
    file_path = tmp_path / "queued.txt"
    file_path.write_text("Queued worker document uses FastAPI.", encoding="utf-8")

    with Session(engine) as session:
        document = Document(
            filename="queued.txt",
            stored_path=str(file_path),
            file_type="txt",
            file_size=file_path.stat().st_size,
            title="queued.txt",
            processing_status="queued",
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        job = create_processing_job(session, "process_document", document.id, "Queued")
        processed = process_next_queued_job(session)

        assert processed is not None
        assert processed.id == job.id
        assert processed.status == "succeeded"

        document = session.get(Document, document.id)
        assert document.processing_status == "ready"
        assert "FastAPI" in document.raw_text


def test_process_next_queued_job_fails_orphan_job():
    with Session(engine) as session:
        job = ProcessingJob(job_type="process_document", status="queued", message="Orphan")
        session.add(job)
        session.commit()
        session.refresh(job)

        processed = process_next_queued_job(session)

        assert processed is not None
        assert processed.id == job.id
        assert processed.status == "failed"
        assert "not linked" in processed.message


def test_process_next_queued_job_stops_after_max_attempts(monkeypatch):
    monkeypatch.setattr(settings, "processing_max_attempts", 2)

    with Session(engine) as session:
        job = ProcessingJob(
            job_type="process_document",
            status="queued",
            message="Too many retries",
            attempts=2,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        processed = process_next_queued_job(session)

        assert processed is not None
        assert processed.id == job.id
        assert processed.status == "failed"
        assert processed.attempts == 2
        assert "Max processing attempts reached" in processed.message


def test_recover_stale_running_job_requeues_when_attempts_remain(monkeypatch):
    monkeypatch.setattr(settings, "processing_stale_minutes", 5)
    monkeypatch.setattr(settings, "processing_max_attempts", 3)

    with Session(engine) as session:
        job = ProcessingJob(
            job_type="process_document",
            status="running",
            message="Interrupted",
            attempts=1,
            started_at=utc_now() - timedelta(minutes=10),
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        recovered = recover_stale_running_jobs(session)

        assert len(recovered) == 1
        assert recovered[0].id == job.id
        assert recovered[0].status == "queued"
        assert recovered[0].started_at is None
        assert "Recovered stale" in recovered[0].message

        recovered[0].status = "failed"
        session.add(recovered[0])
        session.commit()


def test_recover_stale_running_job_fails_when_attempts_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "processing_stale_minutes", 5)
    monkeypatch.setattr(settings, "processing_max_attempts", 2)

    with Session(engine) as session:
        job = ProcessingJob(
            job_type="process_document",
            status="running",
            message="Interrupted",
            attempts=2,
            started_at=utc_now() - timedelta(minutes=10),
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        recovered = recover_stale_running_jobs(session)

        assert len(recovered) == 1
        assert recovered[0].id == job.id
        assert recovered[0].status == "failed"
        assert recovered[0].finished_at is not None
        assert "exceeded max attempts" in recovered[0].message


def test_process_next_queued_job_returns_none_when_queue_empty():
    with Session(engine) as session:
        assert process_next_queued_job(session) is None
