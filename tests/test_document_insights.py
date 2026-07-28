from sqlmodel import Session

from app.db.engine import engine
from app.db.models import Document
from app.services.document_insights import apply_document_insights


def test_apply_document_insights_updates_existing_document():
    with Session(engine) as session:
        document = Document(
            filename="meeting.txt",
            stored_path="data/test_uploads/meeting.txt",
            file_type="txt",
            file_size=10,
            title="meeting.txt",
            raw_text=(
                "Meeting agenda. Deadline is 2026-07-15. Team needs to prepare the launch demo."
            ),
            word_count=12,
            estimated_reading_time_min=1,
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        result = apply_document_insights(session, document)

    assert result["success"] is True
    assert result["document_type"] == "meeting notes"
    assert result["dates"] == 1
    assert result["actions"] >= 1
    assert "2026-07-15" in document.detected_dates
    assert "needs to prepare" in document.action_items


def test_apply_document_insights_skips_document_without_text():
    with Session(engine) as session:
        document = Document(
            filename="blank.txt",
            stored_path="data/test_uploads/blank.txt",
            file_type="txt",
            file_size=10,
            title="blank.txt",
        )
        session.add(document)
        session.commit()
        session.refresh(document)

        result = apply_document_insights(session, document)

    assert result["success"] is False
    assert result["message"] == "No extracted text is available for insights."
