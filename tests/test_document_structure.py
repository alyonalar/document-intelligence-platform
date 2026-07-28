from app.services.document_structure import (
    build_document_structure,
    estimate_pages,
    extract_markdown_headings,
)


def test_estimate_pages_returns_zero_for_empty_document():
    assert estimate_pages(0) == 0


def test_extract_markdown_headings_reads_heading_text():
    headings = extract_markdown_headings("# Intro\n\n## Details\nBody")

    assert headings == ["Intro", "Details"]


def test_build_document_structure_prefers_markdown_headings():
    structure = build_document_structure("# Intro\n\nSome text", "md", word_count=2)

    assert structure["estimated_pages"] == 1
    assert structure["sections"] == ["Intro"]
    assert structure["preview_blocks"]
