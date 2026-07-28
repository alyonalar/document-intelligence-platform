from datetime import date, timedelta
from uuid import uuid4

from sqlmodel import Session

from app.db.engine import engine
from app.db.models import Document
from app.services.actions import (
    action_context,
    action_source_anchor,
    list_document_actions,
    parse_date_value,
    set_action_item_note,
    set_action_item_status,
    summarize_actions,
    timing_for_due_date,
)


def test_list_document_actions_splits_items_and_filters():
    marker = f"demo-{uuid4().hex}"
    with Session(engine) as session:
        document = Document(
            filename="actions-source.txt",
            stored_path="data/test_uploads/actions-source.txt",
            file_type="txt",
            file_size=10,
            title="Actions Source",
            raw_text=f"Before sentence. Team needs to prepare {marker}. After sentence explains why.",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates="2026-07-15",
            action_items=f"Team needs to prepare {marker}.\nOwner should review scope.",
        )
        session.add(document)
        session.commit()

        actions = list_document_actions(
            session,
            query=marker,
            document_type="meeting notes",
            has_dates=True,
        )

    assert len(actions) == 1
    assert actions[0].text == f"Team needs to prepare {marker}."
    assert actions[0].document_type == "meeting notes"
    assert actions[0].dates == ["2026-07-15"]
    assert "Before sentence" in actions[0].context
    assert "After sentence" in actions[0].context


def test_action_context_returns_fallback_when_action_not_found():
    assert (
        action_context("Different text", "Owner should review scope.")
        == "Owner should review scope."
    )


def test_action_source_anchor_points_to_matching_chunk():
    text = "Intro text. " + ("Padding " * 140) + "Owner should review source contract."

    chunk_id, anchor = action_source_anchor(text, "Owner should review source contract.")

    assert chunk_id is not None
    assert anchor == f"#chunk-{chunk_id}"


def test_action_source_anchor_falls_back_to_extracted_text():
    chunk_id, anchor = action_source_anchor("Different text", "Owner should review scope.")

    assert chunk_id is None
    assert anchor == "#extracted-text"


def test_parse_date_value_supports_common_formats():
    assert parse_date_value("2026-07-15") == date(2026, 7, 15)
    assert parse_date_value("July 15, 2026") == date(2026, 7, 15)
    assert parse_date_value("15 \u0438\u044e\u043b\u044f 2026") == date(2026, 7, 15)


def test_timing_for_due_date_labels_overdue_and_upcoming():
    today = date(2026, 6, 10)

    assert timing_for_due_date(today - timedelta(days=1), today=today) == (
        "overdue",
        -1,
        "1 day(s) overdue",
    )
    assert timing_for_due_date(today + timedelta(days=2), today=today) == (
        "upcoming",
        2,
        "Due in 2 day(s)",
    )
    assert timing_for_due_date(None, today=today) == ("no_date", None, "No date")


def test_list_document_actions_sorts_by_due_date_and_filters_timing():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    future = (date.today() + timedelta(days=10)).isoformat()

    with Session(engine) as session:
        overdue = Document(
            filename="overdue-action.txt",
            stored_path="data/test_uploads/overdue-action.txt",
            file_type="txt",
            file_size=10,
            title="Overdue Action",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates=yesterday,
            action_items="Owner should finish overdue item.",
        )
        upcoming = Document(
            filename="upcoming-action.txt",
            stored_path="data/test_uploads/upcoming-action.txt",
            file_type="txt",
            file_size=10,
            title="Upcoming Action",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates=future,
            action_items="Owner should finish upcoming item.",
        )
        session.add(overdue)
        session.add(upcoming)
        session.commit()

        actions = list_document_actions(session, query="finish", document_type="meeting notes")
        overdue_actions = list_document_actions(
            session,
            query="finish",
            document_type="meeting notes",
            timing_status="overdue",
        )

    assert actions[0].due_date == yesterday
    assert actions[0].timing_status == "overdue"
    assert any(action.due_date == future for action in actions)
    assert all(action.timing_status == "overdue" for action in overdue_actions)


def test_summarize_actions_counts_timing_buckets():
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with Session(engine) as session:
        dated = Document(
            filename="summary-dated.txt",
            stored_path="data/test_uploads/summary-dated.txt",
            file_type="txt",
            file_size=10,
            title="Summary Dated",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            detected_dates=yesterday,
            action_items="Owner should finish dated item.",
        )
        no_date = Document(
            filename="summary-no-date.txt",
            stored_path="data/test_uploads/summary-no-date.txt",
            file_type="txt",
            file_size=10,
            title="Summary No Date",
            raw_text="Body",
            word_count=1,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items="Owner should finish undated item.",
        )
        session.add(dated)
        session.add(no_date)
        session.commit()

        actions = list_document_actions(session, query="finish")
        stats = summarize_actions(actions)

    assert stats["total"] >= 2
    assert stats["overdue"] >= 1
    assert stats["no_date"] >= 1


def test_set_action_item_status_marks_done_and_reopens():
    marker = f"close-{uuid4().hex}"
    with Session(engine) as session:
        document = Document(
            filename=f"state-action-{marker}.txt",
            stored_path=f"data/test_uploads/state-action-{marker}.txt",
            file_type="txt",
            file_size=10,
            title="State Action",
            raw_text=f"Owner should close {marker} action.",
            word_count=5,
            estimated_reading_time_min=1,
            document_type="meeting notes",
            action_items=f"Owner should close {marker} action.",
        )
        session.add(document)
        session.commit()

        action = list_document_actions(session, query=marker)[0]
        set_action_item_status(session, action.action_key, "done")

        open_actions = list_document_actions(session, query=marker, completion_status="open")
        done_actions = list_document_actions(session, query=marker, completion_status="done")

        set_action_item_status(session, action.action_key, "open")
        reopened = list_document_actions(session, query=marker, completion_status="open")

    assert not open_actions
    assert len(done_actions) == 1
    assert done_actions[0].completed is True
    assert len(reopened) == 1
    assert reopened[0].completed is False


def test_set_action_item_note_saves_note_and_due_date_override():
    marker = "waiting-on-legal"
    action_marker = f"contract-{uuid4().hex}"
    due_override = (date.today() + timedelta(days=3)).isoformat()
    with Session(engine) as session:
        document = Document(
            filename=f"note-action-{action_marker}.txt",
            stored_path=f"data/test_uploads/note-action-{action_marker}.txt",
            file_type="txt",
            file_size=10,
            title="Note Action",
            raw_text=f"Owner should review the {action_marker} contract.",
            word_count=5,
            estimated_reading_time_min=1,
            document_type="contract",
            action_items=f"Owner should review the {action_marker} contract.",
        )
        session.add(document)
        session.commit()

        action = list_document_actions(session, query=action_marker)[0]
        set_action_item_note(session, action.action_key, marker, due_override)
        actions = list_document_actions(session, query=marker)

    assert len(actions) == 1
    assert actions[0].note == marker
    assert actions[0].due_date == due_override
    assert actions[0].due_date_source == "manual"
    assert actions[0].days_until is not None and actions[0].days_until <= 3
