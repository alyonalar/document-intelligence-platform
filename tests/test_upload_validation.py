from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services import upload_validation
from app.services.upload_validation import (
    get_extension,
    safe_original_filename,
    validate_upload_file,
)


def make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_safe_original_filename_strips_path_parts():
    assert safe_original_filename("../sample.txt") == "sample.txt"


def test_safe_original_filename_strips_windows_path_parts():
    assert safe_original_filename(r"..\nested\sample.txt") == "sample.txt"


def test_get_extension_returns_lowercase_extension():
    assert get_extension("Report.PDF") == "pdf"


def test_validate_upload_file_accepts_pdf_signature():
    filename, extension, size = validate_upload_file(
        make_upload("report.pdf", b"%PDF-1.4\ncontent")
    )

    assert filename == "report.pdf"
    assert extension == "pdf"
    assert size > 0


def test_validate_upload_file_accepts_png_signature():
    filename, extension, size = validate_upload_file(
        make_upload("scan.png", b"\x89PNG\r\n\x1a\ncontent")
    )

    assert filename == "scan.png"
    assert extension == "png"
    assert size > 0


def test_validate_upload_file_rejects_fake_jpeg():
    with pytest.raises(ValueError, match="valid JPEG"):
        validate_upload_file(make_upload("scan.jpg", b"not a jpeg"))


def test_validate_upload_file_rejects_fake_pdf():
    with pytest.raises(ValueError, match="valid PDF"):
        validate_upload_file(make_upload("report.pdf", b"not a pdf"))


def test_validate_upload_file_rejects_binary_text_file():
    with pytest.raises(ValueError, match="text document"):
        validate_upload_file(make_upload("notes.txt", b"text\x00binary"))


def test_validate_upload_file_rejects_file_over_configured_limit(monkeypatch):
    monkeypatch.setattr(upload_validation.settings, "max_file_size_mb", 0)

    with pytest.raises(ValueError, match="Max size is 0 MB"):
        validate_upload_file(make_upload("notes.txt", b"too large for zero limit"))
