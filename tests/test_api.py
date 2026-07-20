from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.engine import engine
from app.db.models import Document, ProcessingJob
from app.main import app
from app.routers.api import normalize_sources
from app.services import processing_jobs

client = TestClient(app)


def create_api_document() -> int:
    with Session(engine) as session:
        document = Document(
            filename=f"api-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api.txt",
            file_type="txt",
            file_size=64,
            title="API Test Document",
            raw_text="The API document explains billing approval and project policy.",
            word_count=9,
            estimated_reading_time_min=1,
            summary_short="API test summary",
            keywords="api, billing, approval",
            document_type="technical doc",
            detected_dates="2026-07-15",
            action_items="Team needs to review billing approval.",
            suggested_questions="What actions or next steps are required?",
            category="documentation",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        return document.id or 0


def test_api_document_search_returns_documents():
    create_api_document()

    response = client.get("/api/documents/search", params={"q": "billing"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["documents"]
    assert "processing_status" in payload["documents"][0]
    assert "processing_label" in payload["documents"][0]
    assert "processing_progress" in payload["documents"][0]
    assert "document_type" in payload["documents"][0]
    assert "suggested_questions" in payload["documents"][0]
    assert "indexed_chunks" in payload["documents"][0]


def test_api_document_search_filters_by_insights():
    with Session(engine) as session:
        meeting = Document(
            filename=f"api-meeting-filter-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-meeting-filter.txt",
            file_type="txt",
            file_size=10,
            title="API Meeting Filter",
            raw_text=(
                "The launch plan has one important next step. "
                "Team needs to prepare API demo. "
                "The customer review depends on it."
            ),
            word_count=2,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates="2026-07-15",
            action_items="Team needs to prepare.",
        )
        invoice = Document(
            filename=f"api-invoice-filter-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-invoice-filter.txt",
            file_type="txt",
            file_size=10,
            title="API Invoice Filter",
            raw_text="Invoice",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="invoice",
        )
        session.add(meeting)
        session.add(invoice)
        session.commit()
        meeting_filename = meeting.filename
        invoice_filename = invoice.filename

    response = client.get(
        "/api/documents/search",
        params={
            "document_type": "meeting notes",
            "has_dates": "true",
            "has_actions": "true",
        },
    )

    assert response.status_code == 200
    documents = response.json()["documents"]
    titles = {document["filename"] for document in documents}
    assert meeting_filename in titles
    assert invoice_filename not in titles


def test_api_actions_endpoint_returns_action_items():
    due_date = (date.today() + timedelta(days=10)).isoformat()
    with Session(engine) as session:
        document = Document(
            filename=f"api-actions-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-actions.txt",
            file_type="txt",
            file_size=10,
            title="API Actions",
            raw_text=(
                "The launch plan has one important next step. "
                "Team needs to prepare API demo. "
                "The customer review depends on it."
            ),
            word_count=2,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates=due_date,
            action_items="Team needs to prepare API demo.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(
        "/api/actions",
        params={
            "q": "API demo",
            "document_type": "meeting notes",
            "has_dates": "true",
            "timing_status": "upcoming",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert "stats" in payload
    assert payload["stats"]["upcoming"] >= 1
    assert any(
        item["document_id"] == document_id
        and item["text"] == "Team needs to prepare API demo."
        and item["dates"] == [due_date]
        and item["due_date"] == due_date
        and item["timing_status"] == "upcoming"
        and item["source_anchor"] == "#chunk-1"
        and item["source_chunk_id"] == 1
        and "customer review" in item["context"]
        for item in payload["actions"]
    )


def test_openapi_exposes_actions_and_insights_response_schemas():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    schemas = payload["components"]["schemas"]

    assert "ActionListResponse" in schemas
    assert "ActionItemResponse" in schemas
    assert "ActionStatusUpdateResponse" in schemas
    assert "ActionNoteUpdateResponse" in schemas
    assert "DocumentInsightsResponse" in schemas
    assert "BulkDocumentInsightsResponse" in schemas

    actions_schema = payload["paths"]["/api/actions"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    insights_schema = payload["paths"]["/api/documents/{document_id}/insights"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert actions_schema["$ref"].endswith("/ActionListResponse")
    assert insights_schema["$ref"].endswith("/DocumentInsightsResponse")


def test_api_actions_status_endpoint_marks_done_and_reopens():
    marker = f"api-close-{uuid4().hex}"
    with Session(engine) as session:
        document = Document(
            filename=f"api-action-state-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-action-state.txt",
            file_type="txt",
            file_size=10,
            title="API Action State",
            raw_text=f"Owner should {marker}.",
            word_count=3,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items=f"Owner should {marker}.",
        )
        session.add(document)
        session.commit()

    list_response = client.get("/api/actions", params={"q": marker})
    action_key = list_response.json()["actions"][0]["action_key"]

    done = client.post(f"/api/actions/{action_key}/status", params={"status_value": "done"})
    assert done.status_code == 200
    assert done.json()["stored_status"] == "done"

    open_list = client.get("/api/actions", params={"q": marker, "completion_status": "open"})
    done_list = client.get("/api/actions", params={"q": marker, "completion_status": "done"})

    assert open_list.json()["total"] == 0
    assert done_list.json()["total"] == 1
    assert done_list.json()["actions"][0]["completed"] is True

    reopened = client.post(f"/api/actions/{action_key}/status", params={"status_value": "open"})
    assert reopened.status_code == 200

    open_again = client.get("/api/actions", params={"q": marker, "completion_status": "open"})
    assert open_again.json()["total"] == 1


def test_api_actions_note_endpoint_saves_note():
    marker = f"api-note-{uuid4().hex}"
    note = f"Waiting on client {uuid4().hex}"
    due_override = (date.today() + timedelta(days=5)).isoformat()
    with Session(engine) as session:
        document = Document(
            filename=f"api-action-note-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-action-note.txt",
            file_type="txt",
            file_size=10,
            title="API Action Note",
            raw_text=f"Owner should handle {marker}.",
            word_count=4,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items=f"Owner should handle {marker}.",
        )
        session.add(document)
        session.commit()

    list_response = client.get("/api/actions", params={"q": marker})
    action_key = list_response.json()["actions"][0]["action_key"]

    response = client.post(
        f"/api/actions/{action_key}/note",
        params={"note": note, "due_date_override": due_override},
    )
    assert response.status_code == 200
    assert response.json()["note"] == note
    assert response.json()["due_date_override"] == due_override

    actions = client.get("/api/actions", params={"q": note})
    assert actions.json()["total"] == 1
    assert actions.json()["actions"][0]["note"] == note
    assert actions.json()["actions"][0]["due_date"] == due_override
    assert actions.json()["actions"][0]["due_date_source"] == "manual"


def test_api_document_detail_returns_structure():
    document_id = create_api_document()

    response = client.get(f"/api/documents/{document_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == document_id
    assert "structure" in payload
    assert payload["structure"]["estimated_pages"] >= 1
    assert payload["processing_status"] == "ready"
    assert payload["document_type"] == "technical doc"
    assert "2026-07-15" in payload["detected_dates"]


def test_api_document_local_ask_returns_answer():
    document_id = create_api_document()

    response = client.post(
        f"/api/documents/{document_id}/ask",
        json={"question": "What approval is mentioned?", "mode": "local"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "What approval is mentioned?"
    assert payload["answer"]
    assert payload["retrieval"] == "keyword"


def test_api_normalize_sources_preserves_page_number():
    sources = normalize_sources(
        [
            {
                "document_id": 1,
                "filename": "scan.pdf",
                "page_number": 3,
                "chunk_id": 2,
                "text": "Evidence",
            }
        ]
    )

    assert sources[0].page_number == 3


def test_api_workspace_ask_requires_document_ids():
    response = client.post(
        "/api/workspace/ask",
        json={"question": "What is shared?", "document_ids": []},
    )

    assert response.status_code == 400


def test_api_compare_documents_returns_diff():
    first_id = create_api_document()
    second_id = create_api_document()

    response = client.post(
        "/api/documents/compare",
        json={"document_ids": [first_id, second_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "diff" in payload
    assert payload["diff"]["keyword_similarity"] >= 0


def test_api_jobs_endpoints_return_processing_jobs():
    document_id = create_api_document()

    with Session(engine) as session:
        job = ProcessingJob(
            job_type="api_test",
            status="succeeded",
            document_id=document_id,
            message="Done",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    list_response = client.get("/api/jobs", params={"status": "succeeded"})
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] >= 1
    assert any(item["id"] == job_id for item in list_payload["jobs"])

    detail_response = client.get(f"/api/jobs/{job_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["message"] == "Done"
    assert detail_response.json()["attempts"] == 0

    document_jobs_response = client.get(f"/api/documents/{document_id}/jobs")
    assert document_jobs_response.status_code == 200
    assert any(item["id"] == job_id for item in document_jobs_response.json()["jobs"])


def test_api_job_detail_returns_404_for_missing_job():
    response = client.get("/api/jobs/999999")

    assert response.status_code == 404


def test_api_process_document_endpoint_creates_job():
    filename = f"api-process-{uuid4().hex}.txt"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("API processing uses FastAPI and OCR jobs.", encoding="utf-8")

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="txt",
            file_size=file_path.stat().st_size,
            title=filename,
            processing_status="failed",
            processing_error="Needs retry.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.post(f"/api/documents/{document_id}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "api_process_document"
    assert payload["status"] == "succeeded"
    assert payload["document_id"] == document_id


def test_api_process_document_endpoint_can_queue_job(monkeypatch):
    monkeypatch.setattr(processing_jobs.settings, "processing_mode", "queued")
    filename = f"api-queued-{uuid4().hex}.txt"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("Queued API processing can be handled by a worker.", encoding="utf-8")

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="txt",
            file_size=file_path.stat().st_size,
            title=filename,
            processing_status="failed",
            processing_error="Needs queued retry.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.post(f"/api/documents/{document_id}/process")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "api_process_document"
    assert payload["status"] == "queued"
    assert payload["document_id"] == document_id

    with Session(engine) as session:
        document = session.get(Document, document_id)
        assert document.processing_status == "queued"
        job = session.get(ProcessingJob, payload["id"])
        processed_job = processing_jobs.run_queued_processing_job(session, job)
        session.refresh(document)

    assert processed_job.status == "succeeded"
    assert document.processing_status == "ready"
    assert "worker" in document.raw_text


def test_api_retry_job_endpoint_creates_retry_job():
    document_id = create_api_document()

    with Session(engine) as session:
        job = ProcessingJob(
            job_type="api_test_retry_source",
            status="failed",
            document_id=document_id,
            message="Original failure",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    response = client.post(f"/api/jobs/{job_id}/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "retry_api_test_retry_source"
    assert payload["document_id"] == document_id


def test_api_retry_job_rejects_job_without_document():
    with Session(engine) as session:
        job = ProcessingJob(
            job_type="orphan",
            status="failed",
            message="No document",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    response = client.post(f"/api/jobs/{job_id}/retry")

    assert response.status_code == 400


def test_api_recompute_document_insights_endpoint():
    with Session(engine) as session:
        document = Document(
            filename=f"api-insights-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-insights.txt",
            file_type="txt",
            file_size=10,
            title="API Insights",
            raw_text="Meeting agenda. Deadline is 2026-07-15. Team needs to prepare.",
            word_count=9,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.post(f"/api/documents/{document_id}/insights")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["document_type"] == "meeting notes"
    assert payload["dates"] == 1
    assert payload["actions"] >= 1
