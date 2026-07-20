from app.services.parsers import extract_text_by_extension, parse_md, parse_txt


def test_parse_txt_reads_utf8_text(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Привет из файла", encoding="utf-8")

    assert parse_txt(str(file_path)) == "Привет из файла"


def test_parse_md_reads_markdown_text(tmp_path):
    file_path = tmp_path / "sample.md"
    file_path.write_text("# Title\n\nBody", encoding="utf-8")

    assert parse_md(str(file_path)) == "# Title\n\nBody"


def test_extract_text_by_extension_returns_blank_for_images(tmp_path):
    file_path = tmp_path / "sample.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    assert extract_text_by_extension(str(file_path), "png") == ""


def test_extract_text_by_extension_rejects_unknown_extension(tmp_path):
    file_path = tmp_path / "sample.unknown"
    file_path.write_text("content", encoding="utf-8")

    try:
        extract_text_by_extension(str(file_path), "unknown")
    except ValueError as exc:
        assert "Unsupported extension" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
