from app.db.models import Document
from app.services.processing_status import build_processing_pipeline


def make_document(status: str, error: str | None = None) -> Document:
    return Document(
        filename=f"{status}.txt",
        stored_path=f"data/test_uploads/{status}.txt",
        file_type="txt",
        file_size=10,
        title=f"{status}.txt",
        processing_status=status,
        processing_error=error,
    )


def test_ready_pipeline_is_complete():
    pipeline = build_processing_pipeline(make_document("ready"))

    assert pipeline["label"] == "Ready for questions"
    assert pipeline["progress"] == 100
    assert all(step["state"] == "complete" for step in pipeline["steps"])


def test_queued_pipeline_marks_worker_step_active():
    pipeline = build_processing_pipeline(make_document("queued"))

    assert pipeline["label"] == "Queued for worker"
    assert pipeline["progress"] == 30
    assert pipeline["steps"][1]["state"] == "active"


def test_failed_pipeline_keeps_error_context():
    pipeline = build_processing_pipeline(make_document("failed", "Parser failed."))

    assert pipeline["label"] == "Processing failed"
    assert pipeline["error"] == "Parser failed."
    assert pipeline["steps"][-1]["state"] == "blocked"
