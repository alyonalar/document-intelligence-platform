import pytest

from app.services.chunking import chunk_pages, chunk_text, chunk_text_records, normalize_text


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  one\n\n two\tthree  ") == "one two three"


def test_chunk_text_returns_empty_list_for_blank_text():
    assert chunk_text("   ") == []


def test_chunk_text_uses_overlap():
    chunks = chunk_text("abcdefghij", chunk_size=6, overlap=2)

    assert chunks == ["abcdef", "efghij"]


def test_chunk_text_records_include_stable_ids():
    records = chunk_text_records("abcdefghij", chunk_size=6, overlap=2)

    assert records == [
        {"chunk_id": 1, "id": 1, "text": "abcdef"},
        {"chunk_id": 2, "id": 2, "text": "efghij"},
    ]


def test_chunk_pages_preserves_page_numbers():
    records = chunk_pages(
        [
            {"page_number": 2, "text": "abcdefghij"},
            {"page_number": 3, "text": "klmnop"},
        ],
        chunk_size=6,
        overlap=2,
    )

    assert records == [
        {"chunk_id": 1, "id": 1, "page_number": 2, "text": "abcdef"},
        {"chunk_id": 2, "id": 2, "page_number": 2, "text": "efghij"},
        {"chunk_id": 3, "id": 3, "page_number": 3, "text": "klmnop"},
    ]


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("content", chunk_size=5, overlap=5)
