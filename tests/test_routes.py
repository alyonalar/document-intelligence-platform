from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db.engine import engine
from app.db.models import (
    Collection,
    CollectionDocumentLink,
    Document,
    DocumentEntity,
    DocumentObligation,
    DocumentRelation,
    DocumentRisk,
    ProcessingJob,
    QAInteraction,
)
from app.main import app
from app.routers import documents as documents_router
from app.routers.documents import build_original_preview, build_source_navigation, preview_snippet
from app.services import processing_jobs, runtime_settings

client = TestClient(app)


def marker_index(response_text: str, marker: str) -> int:
    return response_text.index(marker)


def section_index(response_text: str, section: str) -> int:
    return marker_index(response_text, f'data-section="{section}"')


def get_action_key(query: str) -> str:
    response = client.get("/api/actions", params={"q": query})

    assert response.status_code == 200
    actions = response.json()["actions"]
    assert actions
    return actions[0]["action_key"]


def test_home_page_loads():
    response = client.get("/")

    assert response.status_code == 200
    assert "Document Intelligence Platform" in response.text
    assert "/static/js/jobs.js" in response.text


def test_home_page_prioritizes_upload_and_collapses_operational_sections():
    with Session(engine) as session:
        document = Document(
            filename=f"home-ux-{uuid4().hex}.txt",
            stored_path="data/test_uploads/home-ux.txt",
            file_type="txt",
            file_size=10,
            title="Home UX",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        session.add(
            ProcessingJob(
                job_type="reindex_document",
                status="succeeded",
                document_id=document.id,
                message="Indexed 0 semantic chunk(s).",
            )
        )
        session.commit()

    response = client.get("/")

    assert response.status_code == 200
    upload_index = section_index(response.text, "upload-documents")
    stats_index = section_index(response.text, "document-stats")
    documents_index = section_index(response.text, "document-library")
    jobs_index = section_index(response.text, "processing-jobs")
    admin_index = section_index(response.text, "admin-tools")
    assert stats_index < upload_index < documents_index < jobs_index < admin_index
    assert 'data-testid="processing-jobs-panel"' in response.text
    assert 'data-testid="admin-tools-panel"' in response.text
    assert 'data-testid="document-library-panel"' in response.text


def test_semantic_search_toggle_requires_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runtime_settings, "RUNTIME_SETTINGS_PATH", tmp_path / "runtime_settings.json"
    )
    monkeypatch.setattr(runtime_settings.settings, "openai_api_key", None)
    monkeypatch.setattr(runtime_settings.settings, "chroma_dir", "data/chroma")

    response = client.post(
        "/settings/semantic-search",
        data={"enabled": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "semantic_error=" in response.headers["location"]
    assert runtime_settings.semantic_search_enabled() is False


def test_semantic_search_toggle_persists_runtime_setting(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runtime_settings, "RUNTIME_SETTINGS_PATH", tmp_path / "runtime_settings.json"
    )
    monkeypatch.setattr(runtime_settings.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(runtime_settings.settings, "chroma_dir", "data/chroma")

    response = client.post(
        "/settings/semantic-search",
        data={"enabled": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "semantic_notice=Semantic+search+enabled" in response.headers["location"]
    assert runtime_settings.semantic_search_enabled() is True

    response = client.post(
        "/settings/semantic-search",
        data={"enabled": "false"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert runtime_settings.semantic_search_enabled() is False


def test_language_switcher_sets_cookie_and_renders_russian_mode():
    with TestClient(app) as language_client:
        response = language_client.get("/language/ru?next=/", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "interface_language=ru" in response.headers["set-cookie"]

        response = language_client.get("/")

        assert response.status_code == 200
        assert '<html lang="ru">' in response.text
        assert "Язык" in response.text
        assert "/static/js/i18n.js" in response.text


def test_home_page_renders_russian_filter_values_and_processing_jobs():
    with Session(engine) as session:
        invoice = Document(
            filename=f"ru-home-invoice-{uuid4().hex}.txt",
            stored_path="data/test_uploads/ru-home-invoice.txt",
            file_type="txt",
            file_size=10,
            title="RU Home Invoice",
            raw_text="Invoice text.",
            word_count=2,
            estimated_reading_time_min=1,
            category="documentation",
            document_type="invoice",
        )
        notes = Document(
            filename=f"ru-home-notes-{uuid4().hex}.txt",
            stored_path="data/test_uploads/ru-home-notes.txt",
            file_type="txt",
            file_size=10,
            title="RU Home Notes",
            raw_text="Meeting notes text.",
            word_count=3,
            estimated_reading_time_min=1,
            category="general",
            document_type="meeting notes",
        )
        session.add(invoice)
        session.add(notes)
        session.commit()
        session.refresh(invoice)
        job = ProcessingJob(
            job_type="reindex_document",
            status="succeeded",
            document_id=invoice.id,
            message="Indexed 0 semantic chunk(s).",
        )
        session.add(job)
        session.commit()

    with TestClient(app) as language_client:
        language_client.cookies.set("interface_language", "ru")
        response = language_client.get("/")

    assert response.status_code == 200
    assert "документация" in response.text
    assert "счёт" in response.text
    assert "заметки встречи" in response.text
    assert "переиндексация документа" in response.text
    assert "успешно" in response.text
    assert "Проиндексировано семантических фрагментов: 0." in response.text
    assert "Создано" in response.text
    assert "jobs.js?v=20260701-i18n-jobs" in response.text


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_documents_list_endpoint_returns_json():
    response = client.get("/documents/")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_workspace_loads_without_selected_documents():
    response = client.get("/workspace")

    assert response.status_code == 200
    assert "No documents selected" in response.text


def test_workspace_post_without_selected_documents_redirects_with_error():
    response = client.post("/workspace", data={}, follow_redirects=False)

    assert response.status_code == 303
    assert "workspace_error=" in response.headers["location"]

    response = client.post("/workspace", data={}, follow_redirects=True)

    assert response.status_code == 200
    assert "Select at least one document." in response.text


def test_workspace_compare_page_shows_local_diff():
    with Session(engine) as session:
        first = Document(
            filename="compare-one.txt",
            stored_path="data/test_uploads/compare-one.txt",
            file_type="txt",
            file_size=10,
            title="Compare One",
            raw_text="Billing approval policy.",
            word_count=3,
            estimated_reading_time_min=1,
        )
        second = Document(
            filename="compare-two.txt",
            stored_path="data/test_uploads/compare-two.txt",
            file_type="txt",
            file_size=10,
            title="Compare Two",
            raw_text="Billing approval workflow.",
            word_count=3,
            estimated_reading_time_min=1,
        )
        session.add(first)
        session.add(second)
        session.commit()
        session.refresh(first)
        session.refresh(second)

    response = client.get(f"/workspace/compare?document_ids={first.id}&document_ids={second.id}")

    assert response.status_code == 200
    assert "Local diff" in response.text


def test_preview_snippet_compacts_long_source_text():
    text = "  ".join(["word"] * 40)

    snippet = preview_snippet(text, max_length=32)

    assert len(snippet) <= 32
    assert snippet.endswith("...")
    assert "  " not in snippet


def test_build_source_navigation_limits_pages_and_chunks():
    pages = [{"page_number": index, "text": f"Page {index} body"} for index in range(1, 20)]
    chunks = [
        {"chunk_id": index, "page_number": 1, "text": f"Chunk {index} body"}
        for index in range(1, 30)
    ]

    navigation = build_source_navigation(pages, chunks)

    assert navigation["total_pages"] == 19
    assert navigation["total_chunks"] == 29
    assert len(navigation["pages"]) == 12
    assert len(navigation["chunks"]) == 16
    assert navigation["pages"][0]["snippet"] == "Page 1 body"


def test_document_file_route_serves_previewable_original_inline():
    filename = f"preview-{uuid4().hex}.pdf"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4\npreview")

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="pdf",
            file_size=file_path.stat().st_size,
            title="Preview PDF",
            raw_text="PDF preview text",
            word_count=3,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "inline" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_build_original_preview_includes_pdf_thumbnails_when_backend_available(monkeypatch):
    file_path = Path("data/test_uploads") / f"thumbnail-preview-{uuid4().hex}.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4\npreview")
    document = Document(
        id=123,
        filename="thumbnail-preview.pdf",
        stored_path=str(file_path),
        file_type="pdf",
        file_size=file_path.stat().st_size,
        title="Thumbnail Preview",
    )
    monkeypatch.setattr(documents_router, "pdf_thumbnail_backend_available", lambda: True)
    monkeypatch.setattr(documents_router, "get_pdf_page_count", lambda path: 3)

    preview = build_original_preview(document)

    assert preview is not None
    assert preview["type"] == "pdf"
    assert preview["total_pages"] == 3
    assert preview["thumbnails"][0]["url"] == "/documents/123/thumbnail/1"


def test_document_thumbnail_route_returns_404_without_backend(monkeypatch):
    monkeypatch.setattr(documents_router, "pdf_thumbnail_backend_available", lambda: False)
    filename = f"thumbnail-{uuid4().hex}.pdf"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4\npreview")

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="pdf",
            file_size=file_path.stat().st_size,
            title="Thumbnail PDF",
            raw_text="PDF preview text",
            word_count=3,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/thumbnail/1")

    assert response.status_code == 404
    assert response.json()["detail"] == "PDF thumbnail backend is not available"


def test_document_detail_shows_original_image_preview():
    filename = f"preview-{uuid4().hex}.png"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"\x89PNG\r\n\x1a\npreview")

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="png",
            file_size=file_path.stat().st_size,
            title="Preview Image",
            raw_text="OCR preview text",
            word_count=3,
            estimated_reading_time_min=1,
            processing_status="ready",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/view")

    assert response.status_code == 200
    assert "Original preview" in response.text
    assert f'src="/documents/{document_id}/file"' in response.text
    assert 'data-testid="original-preview-image"' in response.text
    assert 'href="#original-preview"' in response.text
    assert "Original preview available" in response.text


def test_home_page_displays_upload_error_notice():
    response = client.get("/", params={"upload_error": "Unsupported file type"})

    assert response.status_code == 200
    assert "Unsupported file type" in response.text


def test_upload_rejects_unsupported_file_type_with_redirect():
    response = client.post(
        "/documents/upload",
        files={"files": ("sample.exe", b"content", "application/octet-stream")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "upload_report=" in response.headers["location"]


def test_upload_rejects_fake_pdf_with_redirect():
    response = client.post(
        "/documents/upload",
        files={"files": ("fake.pdf", b"not a pdf", "application/pdf")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "upload_report=" in response.headers["location"]


def test_upload_error_page_shows_recovery_guidance():
    response = client.post(
        "/documents/upload",
        files={"files": ("fake.pdf", b"not a pdf", "application/pdf")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Why:" in response.text
    assert "not a real PDF" in response.text
    assert "What to do next:" in response.text
    assert "renaming the extension" in response.text


def test_upload_report_page_shows_mixed_results():
    response = client.post(
        "/documents/upload",
        files=[
            ("files", ("good.txt", b"Project uses FastAPI for document processing.", "text/plain")),
            ("files", ("bad.exe", b"binary", "application/octet-stream")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Upload results" in response.text
    assert "Processing jobs" in response.text
    assert "good.txt" in response.text
    assert "bad.exe" in response.text
    assert "1 uploaded" in response.text
    assert "1 failed" in response.text
    assert "ready" in response.text

    with Session(engine) as session:
        job = session.exec(
            select(ProcessingJob).where(ProcessingJob.job_type == "process_document")
        ).first()
        assert job is not None
        assert job.status in {"succeeded", "failed"}


def test_upload_can_queue_processing_jobs(monkeypatch):
    monkeypatch.setattr(processing_jobs.settings, "processing_mode", "queued")
    filename = f"queued-upload-{uuid4().hex}.txt"

    response = client.post(
        "/documents/upload",
        files={"files": (filename, b"Queued upload waits for the worker.", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Upload results" in response.text
    assert filename in response.text
    assert "1 queued" in response.text
    assert "Uploaded and queued for processing as job" in response.text
    assert "queued" in response.text
    assert "Queued for worker" in response.text

    with Session(engine) as session:
        document = session.exec(select(Document).where(Document.filename == filename)).first()
        assert document is not None
        assert document.processing_status == "queued"
        job = session.exec(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document.id)
            .where(ProcessingJob.status == "queued")
        ).first()
        assert job is not None


def test_upload_empty_text_creates_needs_ocr_document_status():
    filename = f"blank-{uuid4().hex}.txt"
    response = client.post(
        "/documents/upload",
        files={"files": (filename, b"      ", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert filename in response.text
    assert "1 needs OCR" in response.text
    assert "0 failed" in response.text
    assert "needs_ocr" in response.text
    assert "likely needs OCR" in response.text
    assert "What to do next:" in response.text
    assert "OCR_ENABLED=true" in response.text

    with Session(engine) as session:
        document = session.exec(select(Document).where(Document.filename == filename)).first()
        assert document is not None
        assert document.processing_status == "needs_ocr"
        document_id = document.id

    detail = client.get(f"/documents/{document_id}/view")

    assert detail.status_code == 200
    assert "needs_ocr" in detail.text
    assert "likely needs OCR" in detail.text
    assert "What to do next:" in detail.text
    assert "Retry processing after OCR dependencies are configured." in detail.text
    assert "Retry processing" in detail.text


def test_retry_processing_failed_document_marks_it_ready():
    filename = f"retry-{uuid4().hex}.txt"
    file_path = Path("data/test_uploads") / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        "Meeting agenda for FastAPI launch. Deadline is 2026-07-15. "
        "Team needs to prepare local search demo.",
        encoding="utf-8",
    )

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=str(file_path),
            file_type="txt",
            file_size=file_path.stat().st_size,
            title=filename,
            processing_status="failed",
            processing_error="Previous parsing error.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.post(f"/documents/{document_id}/retry")

    assert response.status_code == 200
    assert "Processed and indexed" in response.text
    assert "Processing jobs" in response.text
    assert "Processing pipeline" in response.text
    assert "Ready for questions" in response.text
    assert "Document insights" in response.text
    assert "meeting notes" in response.text
    assert "2026-07-15" in response.text
    assert "Team needs to prepare local search demo." in response.text
    assert f'data-jobs-url="/api/documents/{document_id}/jobs?limit=8"' in response.text
    assert "ready" in response.text

    with Session(engine) as session:
        document = session.get(Document, document_id)
        assert document.processing_status == "ready"
        assert document.processing_error is None
        assert "FastAPI" in document.raw_text
        assert document.document_type == "meeting notes"
        assert "2026-07-15" in document.detected_dates
        assert "needs to prepare" in document.action_items
        assert "What actions or next steps are required?" in document.suggested_questions
        assert document.word_count > 0
        job = session.exec(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        ).first()
        assert job is not None
        assert job.status == "succeeded"


def test_recompute_document_insights_updates_detail_page():
    filename = f"insights-{uuid4().hex}.txt"

    with Session(engine) as session:
        document = Document(
            filename=filename,
            stored_path=f"data/test_uploads/{filename}",
            file_type="txt",
            file_size=10,
            title=filename,
            raw_text=(
                "Meeting agenda for launch. Deadline is 2026-07-15. Team needs to prepare the demo."
            ),
            word_count=14,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.post(f"/documents/{document_id}/recompute-insights")

    assert response.status_code == 200
    assert "Document insights updated." in response.text
    assert "meeting notes" in response.text
    assert "2026-07-15" in response.text
    assert "Team needs to prepare the demo." in response.text

    with Session(engine) as session:
        document = session.get(Document, document_id)
        assert document.document_type == "meeting notes"
        assert "2026-07-15" in document.detected_dates


def test_recompute_all_insights_redirects_with_notice():
    with Session(engine) as session:
        document = Document(
            filename=f"all-insights-{uuid4().hex}.txt",
            stored_path="data/test_uploads/all-insights.txt",
            file_type="txt",
            file_size=10,
            title="All Insights",
            raw_text="Meeting notes. Deadline is 2026-07-15.",
            word_count=6,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()

    response = client.post("/documents/recompute-insights-all", follow_redirects=True)

    assert response.status_code == 200
    assert "Updated insights for" in response.text
    assert "skipped" in response.text


def test_home_filters_by_document_insights():
    with Session(engine) as session:
        meeting = Document(
            filename=f"meeting-filter-{uuid4().hex}.txt",
            stored_path="data/test_uploads/meeting-filter.txt",
            file_type="txt",
            file_size=10,
            title="Meeting Filter",
            raw_text=(
                "The launch plan has one important next step. "
                "Team needs to prepare dashboard demo. "
                "The customer review depends on it."
            ),
            word_count=2,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates="2026-07-15",
            action_items="Team needs to prepare.",
        )
        invoice = Document(
            filename=f"invoice-filter-{uuid4().hex}.txt",
            stored_path="data/test_uploads/invoice-filter.txt",
            file_type="txt",
            file_size=10,
            title="Invoice Filter",
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
        "/",
        params={
            "document_type": "meeting notes",
            "has_dates": "true",
            "has_actions": "true",
        },
    )

    assert response.status_code == 200
    assert meeting_filename in response.text
    assert invoice_filename not in response.text
    assert "Has dates" in response.text
    assert "1 date(s)" in response.text
    assert "1 action(s)" in response.text


def test_actions_dashboard_lists_and_exports_action_items():
    due_date = (date.today() + timedelta(days=10)).isoformat()
    with Session(engine) as session:
        document = Document(
            filename=f"dashboard-actions-{uuid4().hex}.txt",
            stored_path="data/test_uploads/dashboard-actions.txt",
            file_type="txt",
            file_size=10,
            title="Dashboard Actions",
            raw_text=(
                "The launch plan has one important next step. "
                "Team needs to prepare dashboard demo. "
                "The customer review depends on it."
            ),
            word_count=2,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates=due_date,
            action_items="Team needs to prepare dashboard demo.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(
        "/actions",
        params={"q": "dashboard", "has_dates": "true", "timing_status": "upcoming"},
    )

    assert response.status_code == 200
    assert "Document Actions" in response.text
    assert 'data-testid="actions-report-download"' in response.text
    assert "Download report (.md)" in response.text
    assert "Due soon" in response.text
    assert "Team needs to prepare dashboard demo." in response.text
    assert "Mark done" in response.text
    assert "The launch plan has one important next step." in response.text
    assert "The customer review depends on it." in response.text
    assert f"/documents/{document_id}/view#chunk-1" in response.text
    assert "source chunk 1" in response.text
    assert due_date in response.text
    assert "Due in" in response.text

    export = client.get(
        "/actions/export.md",
        params={"q": "dashboard", "has_dates": "true", "timing_status": "upcoming"},
    )

    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown")
    assert "Team needs to prepare dashboard demo." in export.text
    assert "Timing: Due in" in export.text
    assert f"Source: /documents/{document_id}/view#chunk-1" in export.text
    assert "Due soon:" in export.text
    assert "Context:" in export.text
    assert "Status: open" in export.text


def test_actions_dashboard_can_mark_done_and_reopen():
    marker = f"close-{uuid4().hex}"
    with Session(engine) as session:
        document = Document(
            filename=f"done-actions-{uuid4().hex}.txt",
            stored_path="data/test_uploads/done-actions.txt",
            file_type="txt",
            file_size=10,
            title="Done Actions",
            raw_text="Owner should close dashboard action.",
            word_count=5,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items=f"Owner should {marker} dashboard action.",
        )
        session.add(document)
        session.commit()

    action_key = get_action_key(marker)

    done = client.post(
        f"/actions/{action_key}/status",
        data={"status_value": "done", "q": marker, "completion_status": "all"},
        follow_redirects=True,
    )
    assert done.status_code == 200
    assert "Reopen" in done.text
    assert "done" in done.text

    reopened = client.post(
        f"/actions/{action_key}/status",
        data={"status_value": "open", "q": marker, "completion_status": "open"},
        follow_redirects=True,
    )
    assert reopened.status_code == 200
    assert "Mark done" in reopened.text


def test_actions_dashboard_can_save_note():
    marker = f"note-{uuid4().hex}"
    due_override = (date.today() + timedelta(days=4)).isoformat()
    with Session(engine) as session:
        document = Document(
            filename=f"note-actions-{uuid4().hex}.txt",
            stored_path="data/test_uploads/note-actions.txt",
            file_type="txt",
            file_size=10,
            title="Note Actions",
            raw_text=f"Owner should handle {marker}.",
            word_count=4,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items=f"Owner should handle {marker}.",
        )
        session.add(document)
        session.commit()

    action_key = get_action_key(marker)

    response = client.post(
        f"/actions/{action_key}/note",
        data={
            "note": "Waiting on client",
            "due_date_override": due_override,
            "q": marker,
            "completion_status": "open",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Waiting on client" in response.text
    assert "manual date" in response.text
    assert "Due in" in response.text


def test_home_page_shows_collections_section():
    response = client.get("/")

    assert response.status_code == 200
    assert "Collections" in response.text


def test_create_collection_redirects_with_notice():
    name = f"Test Collection {uuid4().hex}"
    response = client.post(
        "/collections/create",
        data={"name": name, "description": "Created by route test"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "collection_notice=" in response.headers["location"]


def test_create_collection_rejects_duplicate_name():
    name = f"Duplicate Collection {uuid4().hex}"
    with Session(engine) as session:
        session.add(Collection(name=name))
        session.commit()

    response = client.post(
        "/collections/create",
        data={"name": name, "description": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "collection_error=" in response.headers["location"]


def test_create_collection_rejects_empty_name_with_redirect():
    response = client.post("/collections/create", data={}, follow_redirects=False)

    assert response.status_code == 303
    assert "collection_error=" in response.headers["location"]
    assert response.headers["location"].endswith("#collections")

    response = client.post("/collections/create", data={}, follow_redirects=True)

    assert response.status_code == 200
    assert "Collection name is required." in response.text


def test_home_page_can_add_single_document_to_empty_collection():
    with Session(engine) as session:
        document = Document(
            filename=f"single-add-{uuid4().hex}.txt",
            stored_path="data/test_uploads/single-add.txt",
            file_type="txt",
            file_size=10,
            title="Single Add",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
        )
        collection = Collection(name=f"Empty Target {uuid4().hex}")
        session.add(document)
        session.add(collection)
        session.commit()
        session.refresh(document)
        session.refresh(collection)
        document_id = document.id
        collection_id = collection.id
        collection_name = collection.name

    response = client.get("/")

    assert response.status_code == 200
    assert collection_name in response.text
    assert f'form="add-doc-{document_id}"' in response.text
    assert "Add to collection" in response.text

    response = client.post(
        "/collections/add-documents",
        data={"collection_id": str(collection_id), "document_ids": str(document_id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("#collections")
    with Session(engine) as session:
        link = session.get(CollectionDocumentLink, (collection_id, document_id))
        assert link is not None


def test_collection_detail_page_loads():
    with Session(engine) as session:
        collection = Collection(name=f"Detail Collection {uuid4().hex}")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    response = client.get(f"/collections/{collection_id}")

    assert response.status_code == 200
    assert "Documents" in response.text
    assert "Export Markdown" in response.text
    assert "Edit collection" in response.text


def test_update_collection_changes_name_and_description():
    with Session(engine) as session:
        collection = Collection(name=f"Old Collection {uuid4().hex}", description="Old")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    new_name = f"Updated Collection {uuid4().hex}"
    response = client.post(
        f"/collections/{collection_id}/update",
        data={"name": new_name, "description": "New description"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Updated collection:" in response.text
    assert new_name in response.text
    assert "New description" in response.text

    with Session(engine) as session:
        collection = session.get(Collection, collection_id)
        assert collection.name == new_name
        assert collection.description == "New description"


def test_update_collection_rejects_empty_name():
    with Session(engine) as session:
        collection = Collection(name=f"Keep Name {uuid4().hex}", description="Original")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    response = client.post(
        f"/collections/{collection_id}/update",
        data={"name": "   ", "description": "Changed"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Collection name is required." in response.text

    with Session(engine) as session:
        collection = session.get(Collection, collection_id)
        assert collection.description == "Original"


def test_update_collection_rejects_duplicate_name():
    with Session(engine) as session:
        target = Collection(name=f"Target Collection {uuid4().hex}")
        existing = Collection(name=f"Existing Collection {uuid4().hex}")
        session.add(target)
        session.add(existing)
        session.commit()
        session.refresh(target)
        session.refresh(existing)
        target_id = target.id
        existing_name = existing.name

    response = client.post(
        f"/collections/{target_id}/update",
        data={"name": existing_name, "description": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Collection already exists:" in response.text

    with Session(engine) as session:
        target = session.get(Collection, target_id)
        assert target.name != existing_name


def test_remove_document_from_collection_redirects_and_deletes_link():
    with Session(engine) as session:
        collection = Collection(name=f"Remove Collection {uuid4().hex}")
        document = Document(
            filename="remove-test.txt",
            stored_path="data/uploads/remove-test.txt",
            file_type="txt",
            file_size=5,
            title="Remove Test",
            word_count=1,
            estimated_reading_time_min=1,
        )
        session.add(collection)
        session.add(document)
        session.commit()
        session.refresh(collection)
        session.refresh(document)

        session.add(
            CollectionDocumentLink(
                collection_id=collection.id,
                document_id=document.id,
            )
        )
        session.commit()
        collection_id = collection.id
        document_id = document.id

    response = client.post(
        f"/collections/{collection_id}/remove-document",
        data={"document_id": document_id},
        follow_redirects=False,
    )

    assert response.status_code == 303

    with Session(engine) as session:
        link = session.get(CollectionDocumentLink, (collection_id, document_id))
        assert link is None


def test_delete_collection_redirects():
    with Session(engine) as session:
        collection = Collection(name=f"Delete Collection {uuid4().hex}")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    response = client.post(
        f"/collections/{collection_id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "collection_notice=" in response.headers["location"]
    assert response.headers["location"].endswith("#collections")


def test_export_document_markdown_endpoint_returns_attachment():
    with Session(engine) as session:
        document = Document(
            filename="export-test.txt",
            stored_path="data/uploads/export-test.txt",
            file_type="txt",
            file_size=12,
            title="Export Test",
            raw_text="Export body",
            word_count=2,
            estimated_reading_time_min=1,
            summary_short="Export summary",
            action_items="Owner should export only actions.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/export.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "# Export Test" in response.text

    filtered = client.get(
        f"/documents/{document_id}/export.md",
        params={"sections": "actions"},
    )

    assert filtered.status_code == 200
    assert "Owner should export only actions." in filtered.text
    assert "Export summary" not in filtered.text
    assert "Extracted Text" not in filtered.text


def test_document_detail_page_shows_structure():
    with Session(engine) as session:
        document = Document(
            filename="structure-test.md",
            stored_path="data/test_uploads/structure-test.md",
            file_type="md",
            file_size=24,
            title="Structure Test",
            raw_text="# Heading\n\nBody",
            word_count=2,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/view")

    assert response.status_code == 200
    assert "Document structure" in response.text
    assert "Source map" in response.text
    assert "Jump to extracted pages and chunks used by citations." in response.text
    assert 'href="#extracted-text"' in response.text
    assert 'href="#chunk-1"' in response.text
    assert "Heading" in response.text
    assert 'id="extracted-text"' in response.text
    assert 'id="chunk-1"' in response.text
    assert "Pages" in response.text
    assert 'id="page-1"' in response.text


def test_document_detail_page_renders_russian_interface():
    with Session(engine) as session:
        document = Document(
            filename="ru-detail-test.txt",
            stored_path="data/test_uploads/ru-detail-test.txt",
            file_type="txt",
            file_size=42,
            title="RU Detail Test",
            raw_text="Policy starts on 2026-09-01. Contact support@example.org.",
            word_count=8,
            estimated_reading_time_min=1,
            category="documentation",
            processing_status="ready",
            document_type="general document",
            detected_dates="2026-09-01",
            suggested_questions=(
                "What are the most important points in this document?\n"
                "What should I pay attention to before using this document?\n"
                "Which dates or deadlines are mentioned?\n"
                "What does the document say about policy?"
            ),
            keywords="policy, support",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    with TestClient(app) as language_client:
        language_client.cookies.set("interface_language", "ru")
        response = language_client.get(f"/documents/{document_id}/view")

    assert response.status_code == 200
    assert "Исходное имя файла" in response.text
    assert "Количество слов" in response.text
    assert "Пайплайн обработки" in response.text
    assert "Переиндексировать документ" in response.text
    assert "Спросить по этому документу" in response.text
    assert "Карта источников" in response.text
    assert "Инсайты документа" in response.text
    assert "Какие самые важные пункты в этом документе?" in response.text
    assert 'data-question-suggestion="Какие даты или дедлайны упомянуты?"' in response.text
    assert "Что документ говорит о policy?" in response.text
    assert "Структура документа" in response.text
    assert "Краткая сводка" in response.text
    assert "Ключевые слова" in response.text
    assert "<h3>Generated FAQ Drafts</h3>" not in response.text


def test_document_detail_hides_stale_phone_entities_that_are_dates():
    with Session(engine) as session:
        document = Document(
            filename="phone-date-entity-test.txt",
            stored_path="data/test_uploads/phone-date-entity-test.txt",
            file_type="txt",
            file_size=42,
            title="Phone Date Entity Test",
            raw_text="Meeting date 10.09.2026.",
            word_count=3,
            estimated_reading_time_min=1,
            processing_status="ready",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        session.add(
            DocumentEntity(
                document_id=document.id,
                entity_type="date",
                value="10.09.2026",
                normalized_value="10.09.2026",
            )
        )
        session.add(
            DocumentEntity(
                document_id=document.id,
                entity_type="phone",
                value="10.09.2026. 2",
                normalized_value="100920262",
            )
        )
        session.commit()
        document_id = document.id

    response = client.get(f"/documents/{document_id}/view")

    assert response.status_code == 200
    assert "<strong>date</strong>: 10.09.2026" in response.text
    assert "<strong>phone</strong>: 10.09.2026" not in response.text
    assert "<strong>phone</strong>: 10.09.2026. 2" not in response.text


def test_document_ask_route_renders_after_saving_history():
    with Session(engine) as session:
        document = Document(
            filename="ask-route-test.txt",
            stored_path="data/test_uploads/ask-route-test.txt",
            file_type="txt",
            file_size=64,
            title="Ask Route Test",
            raw_text="The most important point is to validate support escalation rules.",
            word_count=10,
            estimated_reading_time_min=1,
            processing_status="ready",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(
        f"/documents/{document_id}/ask",
        params={
            "question": "What are the most important points in this document?",
            "mode": "local",
        },
    )

    assert response.status_code == 200
    assert "Ask Route Test" in response.text
    assert "Answer" in response.text
    assert 'action="/documents/' in response.text
    assert '/ask#ask-document"' in response.text


def test_document_ask_route_translates_local_fallback_in_russian_mode():
    with Session(engine) as session:
        document = Document(
            filename="ru-ask-fallback-test.txt",
            stored_path="data/test_uploads/ru-ask-fallback-test.txt",
            file_type="txt",
            file_size=64,
            title="RU Ask Fallback Test",
            raw_text="Alpha beta gamma.",
            word_count=3,
            estimated_reading_time_min=1,
            processing_status="ready",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    with TestClient(app) as language_client:
        language_client.cookies.set("interface_language", "ru")
        response = language_client.get(
            f"/documents/{document_id}/ask",
            params={"question": "Какие даты или дедлайны упомянуты?", "mode": "local"},
        )

    assert response.status_code == 200
    assert "Не удалось найти явный ответ в этом документе." in response.text


def test_document_detail_collapses_and_deletes_recent_questions():
    with Session(engine) as session:
        document = Document(
            filename="document-history-delete-test.txt",
            stored_path="data/test_uploads/document-history-delete-test.txt",
            file_type="txt",
            file_size=64,
            title="Document History Delete Test",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            processing_status="ready",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        interaction = QAInteraction(
            scope="document",
            question="Can I delete this?",
            answer="Yes.",
            document_ids=f",{document.id},",
        )
        session.add(interaction)
        session.commit()
        session.refresh(interaction)
        document_id = document.id
        interaction_id = interaction.id

    response = client.get(f"/documents/{document_id}/view")

    assert response.status_code == 200
    assert 'data-section="recent-questions"' in response.text
    assert 'data-testid="recent-questions-panel"' in response.text
    assert "Can I delete this?" in response.text
    assert f'action="/documents/{document_id}/history/{interaction_id}/delete"' in response.text

    response = client.post(
        f"/documents/{document_id}/history/{interaction_id}/delete",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/documents/{document_id}/view#recent-questions")
    with Session(engine) as session:
        assert session.get(QAInteraction, interaction_id) is None


def test_action_status_form_accepts_empty_document_id_and_redirects():
    with Session(engine) as session:
        document = Document(
            filename="action-status-test.txt",
            stored_path="data/test_uploads/action-status-test.txt",
            file_type="txt",
            file_size=80,
            title="Action Status Test",
            raw_text="Owner should send the report by 2026-08-28.",
            word_count=8,
            estimated_reading_time_min=1,
            document_type="invoice",
            detected_dates="2026-08-28",
            action_items="Owner should send the report by 2026-08-28.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)

    action_key = get_action_key("send the report")
    response = client.post(
        f"/actions/{action_key}/status",
        data={
            "status_value": "done",
            "q": "",
            "document_type": "",
            "document_id": "None",
            "has_dates": "",
            "timing_status": "",
            "completion_status": "open",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/actions?completion_status=all")

    response = client.post(
        f"/actions/{action_key}/status",
        data={
            "status_value": "done",
            "q": "",
            "document_type": "",
            "document_id": "",
            "has_dates": "",
            "timing_status": "",
            "completion_status": "open",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Action Status Test" in response.text
    assert "done" in response.text


def test_action_status_form_accepts_translated_values_from_legacy_russian_page():
    with Session(engine) as session:
        document = Document(
            filename="action-status-russian-values-test.txt",
            stored_path="data/test_uploads/action-status-russian-values-test.txt",
            file_type="txt",
            file_size=80,
            title="Action Status Russian Values Test",
            raw_text="Owner should update the FAQ by 2026-09-10.",
            word_count=8,
            estimated_reading_time_min=1,
            document_type="general document",
            detected_dates="2026-09-10",
            action_items="Owner should update the FAQ by 2026-09-10.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)

    action_key = get_action_key("update the FAQ")
    response = client.post(
        f"/actions/{action_key}/status",
        data={
            "status_value": "готово",
            "q": "",
            "document_type": "",
            "document_id": "",
            "has_dates": "",
            "timing_status": "",
            "completion_status": "готово",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/actions?completion_status=done")

    response = client.post(
        f"/actions/{action_key}/status",
        data={
            "status_value": "открыто",
            "q": "",
            "document_type": "",
            "document_id": "",
            "has_dates": "",
            "timing_status": "",
            "completion_status": "готово",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/actions?completion_status=all")


def test_client_i18n_does_not_translate_form_values():
    script = Path("app/static/js/i18n.js").read_text(encoding="utf-8")

    assert '"value"' not in script


def test_delete_document_removes_collection_links():
    with Session(engine) as session:
        document = Document(
            filename="collection-delete-test.txt",
            stored_path="data/test_uploads/collection-delete-test.txt",
            file_type="txt",
            file_size=10,
            title="Collection Delete Test",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
        )
        collection = Collection(name=f"Delete Link {uuid4().hex}")
        session.add(document)
        session.add(collection)
        session.commit()
        session.refresh(document)
        session.refresh(collection)
        session.add(CollectionDocumentLink(collection_id=collection.id, document_id=document.id))
        session.commit()
        document_id = document.id
        collection_id = collection.id

    response = client.post(f"/documents/{document_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    with Session(engine) as session:
        links = session.exec(
            select(CollectionDocumentLink).where(
                CollectionDocumentLink.collection_id == collection_id
            )
        ).all()
    assert links == []


def test_delete_document_removes_all_document_owned_records():
    with Session(engine) as session:
        document = Document(
            filename="cascade-delete-test.txt",
            stored_path="data/test_uploads/cascade-delete-test.txt",
            file_type="txt",
            file_size=10,
            title="Cascade Delete Test",
            raw_text="Atlas LLP must pay a penalty.",
            action_items="Atlas LLP must pay.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        entity = DocumentEntity(
            document_id=document.id,
            entity_type="organization",
            value="Atlas LLP",
            normalized_value="atlas llp",
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)
        session.add(
            DocumentRelation(
                source_document_id=document.id, source_entity_id=entity.id, relation_type="mentions"
            )
        )
        session.add(
            DocumentObligation(
                document_id=document.id, subject="Atlas LLP", action="pay", source_text="must pay"
            )
        )
        session.add(
            DocumentRisk(
                document_id=document.id,
                risk_type="penalty",
                title="Penalty",
                description="Detected",
                severity="high",
                source_text="penalty",
            )
        )
        session.add(ProcessingJob(job_type="process_document", document_id=document.id))
        session.add(
            QAInteraction(
                scope="document", question="Q", answer="A", document_ids=f",{document.id},"
            )
        )
        session.commit()
        document_id = document.id

    response = client.post(f"/documents/{document_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    with Session(engine) as session:
        assert session.get(Document, document_id) is None
        assert (
            session.exec(
                select(DocumentEntity).where(DocumentEntity.document_id == document_id)
            ).all()
            == []
        )
        assert (
            session.exec(
                select(DocumentRelation).where(DocumentRelation.source_document_id == document_id)
            ).all()
            == []
        )
        assert (
            session.exec(
                select(DocumentObligation).where(DocumentObligation.document_id == document_id)
            ).all()
            == []
        )
        assert (
            session.exec(select(DocumentRisk).where(DocumentRisk.document_id == document_id)).all()
            == []
        )
        assert (
            session.exec(
                select(ProcessingJob).where(ProcessingJob.document_id == document_id)
            ).all()
            == []
        )
        assert (
            session.exec(
                select(QAInteraction).where(QAInteraction.document_ids.contains(f",{document_id},"))
            ).all()
            == []
        )


def test_export_document_docx_endpoint_returns_attachment():
    with Session(engine) as session:
        document = Document(
            filename="export-docx-test.txt",
            stored_path="data/uploads/export-docx-test.txt",
            file_type="txt",
            file_size=12,
            title="Export DOCX Test",
            raw_text="Export body",
            word_count=2,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/export.docx")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"PK")


def test_export_document_pdf_endpoint_returns_attachment():
    with Session(engine) as session:
        document = Document(
            filename="export-pdf-test.txt",
            stored_path="data/uploads/export-pdf-test.txt",
            file_type="txt",
            file_size=12,
            title="Export PDF Test",
            raw_text="Export PDF body",
            word_count=3,
            estimated_reading_time_min=1,
            action_items="Owner should export PDF actions.",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        document_id = document.id

    response = client.get(f"/documents/{document_id}/export.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-1.4")
    assert b"Export PDF Test" in response.content

    filtered = client.get(
        f"/documents/{document_id}/export.pdf",
        params={"sections": "actions"},
    )

    assert filtered.status_code == 200
    assert b"Owner should export PDF actions." in filtered.content
    assert b"Export PDF body" not in filtered.content


def test_export_collection_markdown_endpoint_returns_attachment():
    with Session(engine) as session:
        collection = Collection(name=f"Export Collection {uuid4().hex}")
        document = Document(
            filename=f"collection-export-{uuid4().hex}.txt",
            stored_path="data/test_uploads/collection-export.txt",
            file_type="txt",
            file_size=10,
            title="Collection Export Doc",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            summary_short="Collection summary only.",
        )
        session.add(collection)
        session.add(document)
        session.commit()
        session.refresh(collection)
        session.refresh(document)
        session.add(CollectionDocumentLink(collection_id=collection.id, document_id=document.id))
        session.commit()
        collection_id = collection.id

    response = client.get(f"/collections/{collection_id}/export.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert "Export Collection" in response.text

    filtered = client.get(
        f"/collections/{collection_id}/export.md",
        params={"sections": "summaries"},
    )

    assert filtered.status_code == 200
    assert "Collection summary only." in filtered.text
    assert "Filename:" not in filtered.text


def test_export_collection_docx_endpoint_returns_attachment():
    with Session(engine) as session:
        collection = Collection(name=f"Export DOCX Collection {uuid4().hex}")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    response = client.get(f"/collections/{collection_id}/export.docx")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"PK")


def test_export_collection_pdf_endpoint_returns_attachment():
    with Session(engine) as session:
        collection = Collection(name=f"Export PDF Collection {uuid4().hex}")
        session.add(collection)
        session.commit()
        session.refresh(collection)
        collection_id = collection.id

    response = client.get(f"/collections/{collection_id}/export.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-1.4")
    assert b"Export PDF Collection" in response.content


def test_export_missing_collection_returns_404():
    response = client.get("/collections/999999/export.md")

    assert response.status_code == 404


def test_history_page_loads():
    response = client.get("/history")

    assert response.status_code == 200
    assert "Question History" in response.text


def test_history_export_returns_markdown_attachment():
    with Session(engine) as session:
        interaction = QAInteraction(
            scope="document",
            question=f"Export history {uuid4().hex}",
            answer="History answer",
            document_ids=",1,",
            retrieval="keyword",
            sources='["Route evidence"]',
        )
        session.add(interaction)
        session.commit()

    response = client.get("/history/export.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Question History" in response.text
    assert "Route evidence" in response.text


def test_history_page_links_sources_to_documents():
    with Session(engine) as session:
        document = Document(
            filename="source-link.txt",
            stored_path="data/test_uploads/source-link.txt",
            file_type="txt",
            file_size=12,
            title="Source Link",
            raw_text="Evidence body",
            word_count=2,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        interaction = QAInteraction(
            scope="document",
            question=f"Source link {uuid4().hex}",
            answer="History answer",
            document_ids=f",{document.id},",
            retrieval="keyword",
            sources=f'[{{"document_id": {document.id}, "filename": "source-link.txt", "page_number": 3, "chunk_id": 1, "text": "Evidence body"}}]',
        )
        session.add(interaction)
        session.commit()
        document_id = document.id

    response = client.get("/history")

    assert response.status_code == 200
    assert f"/documents/{document_id}/view#chunk-1" in response.text
    assert f"/documents/{document_id}/view#page-3" in response.text


def test_delete_history_entry_redirects():
    with Session(engine) as session:
        interaction = QAInteraction(
            scope="document",
            question=f"Delete history {uuid4().hex}",
            answer="Delete me",
            document_ids=",1,",
        )
        session.add(interaction)
        session.commit()
        session.refresh(interaction)
        interaction_id = interaction.id

    response = client.post(
        f"/history/{interaction_id}/delete",
        data={"q": "", "scope": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/history" in response.headers["location"]
