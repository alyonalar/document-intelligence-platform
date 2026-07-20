from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.engine import engine
from app.db.models import Document, DocumentEntity
from app.main import app
from app.services.intelligence_pipeline import process_document_intelligence

client = TestClient(app)


def create_intelligence_document() -> int:
    with Session(engine) as session:
        text = "Contract no. API-1 with TOO ApiTest. Atlas LLP must pay 1000 KZT no later than 2026-02-01. Penalty applies."
        document = Document(
            filename=f"api-intel-{uuid4().hex}.txt",
            stored_path="data/test_uploads/api-intel.txt",
            file_type="txt",
            file_size=len(text),
            title="API Intelligence",
            raw_text=text,
            word_count=len(text.split()),
            estimated_reading_time_min=1,
            summary_short="API intelligence summary",
        )
        session.add(document)
        session.commit()
        session.refresh(document)
        process_document_intelligence(session, document)
        return document.id


def test_intelligence_api_smoke_endpoints():
    document_id = create_intelligence_document()
    for path in [
        f"/api/documents/{document_id}/intelligence/recompute",
        f"/api/documents/{document_id}/entities",
        f"/api/documents/{document_id}/relations",
        f"/api/documents/{document_id}/graph",
        f"/api/documents/{document_id}/obligations",
        f"/api/documents/{document_id}/risks",
        "/api/intelligence/summary",
        "/api/obligations",
        "/api/obligations/summary",
        "/api/risks",
        "/api/risks/summary",
    ]:
        response = (
            client.post(path) if path.endswith("/intelligence/recompute") else client.get(path)
        )
        assert response.status_code == 200


def test_entities_api_hides_stale_phone_entities_that_are_dates():
    with Session(engine) as session:
        document = Document(
            filename=f"stale-phone-date-{uuid4().hex}.txt",
            stored_path="data/test_uploads/stale-phone-date.txt",
            file_type="txt",
            file_size=24,
            title="Stale Phone Date",
            raw_text="Meeting date 10.09.2026.",
            word_count=3,
            estimated_reading_time_min=1,
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

    response = client.get(f"/api/documents/{document_id}/entities")

    assert response.status_code == 200
    entities = response.json()
    assert any(item["entity_type"] == "date" and item["value"] == "10.09.2026" for item in entities)
    assert not any(item["entity_type"] == "phone" for item in entities)


def test_openapi_exposes_intelligence_schemas():
    response = client.get("/openapi.json")
    schemas = response.json()["components"]["schemas"]
    assert "DocumentEntityResponse" in schemas
    assert "GraphResponse" in schemas
    assert "DocumentObligationResponse" in schemas
    assert "DocumentRiskResponse" in schemas
