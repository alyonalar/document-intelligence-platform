import pytest

from app.services import ocr


def test_ocr_is_unavailable_when_disabled(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_enabled", False)

    assert ocr.ocr_available() is False
    assert "OCR is disabled" in ocr.explain_ocr_unavailable("pdf")


def test_ocr_status_reports_missing_command(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr.settings, "ocr_engine", "tesseract")
    monkeypatch.setattr(ocr.settings, "tesseract_cmd", "definitely-missing-tesseract")
    monkeypatch.setattr(ocr, "missing_python_packages", lambda: [])

    status = ocr.ocr_status()

    assert status["enabled"] is True
    assert status["available"] is False
    assert status["command_found"] is False


def test_ocr_status_reports_missing_python_packages(monkeypatch):
    monkeypatch.setattr(ocr.settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr.settings, "ocr_engine", "tesseract")
    monkeypatch.setattr(ocr, "missing_python_packages", lambda: ["pdf2image"])
    monkeypatch.setattr(ocr, "tesseract_command_found", lambda: True)

    status = ocr.ocr_status()

    assert status["available"] is False
    assert status["missing_python_packages"] == ["pdf2image"]
    assert "Missing OCR Python packages" in ocr.explain_ocr_unavailable("pdf")


def test_extract_text_with_ocr_rejects_unsupported_extension(tmp_path):
    file_path = tmp_path / "image.txt"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(ocr.OCRUnavailableError) as exc:
        ocr.extract_text_with_ocr(str(file_path), "txt")

    assert "OCR is only prepared" in str(exc.value)


def test_extract_text_with_ocr_uses_pdf_tesseract_path(monkeypatch, tmp_path):
    file_path = tmp_path / "scan.pdf"
    file_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(ocr.settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr.settings, "ocr_engine", "tesseract")
    monkeypatch.setattr(ocr, "ocr_available", lambda: True)
    monkeypatch.setattr(
        ocr,
        "extract_pdf_text_with_tesseract",
        lambda path: "Text extracted from scan" if path == str(file_path) else "",
    )

    assert ocr.extract_text_with_ocr(str(file_path), "pdf") == "Text extracted from scan"


def test_extract_text_with_ocr_uses_image_tesseract_path(monkeypatch, tmp_path):
    file_path = tmp_path / "scan.png"
    file_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(ocr.settings, "ocr_enabled", True)
    monkeypatch.setattr(ocr.settings, "ocr_engine", "tesseract")
    monkeypatch.setattr(ocr, "ocr_available", lambda: True)
    monkeypatch.setattr(
        ocr,
        "extract_image_text_with_tesseract",
        lambda path: "Text extracted from image" if path == str(file_path) else "",
    )

    assert ocr.extract_text_with_ocr(str(file_path), "png") == "Text extracted from image"


def test_preprocess_image_for_ocr_converts_and_scales(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    monkeypatch.setattr(ocr.settings, "ocr_preprocess_images", True)
    monkeypatch.setattr(ocr.settings, "ocr_image_target_width", 200)
    monkeypatch.setattr(ocr.settings, "ocr_contrast_factor", 1.5)

    image = Image.new("RGB", (100, 50), color="white")
    processed = ocr.preprocess_image_for_ocr(image)

    assert processed.mode == "L"
    assert processed.width == 200
    assert processed.height == 100


def test_preprocess_image_for_ocr_can_be_disabled(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    monkeypatch.setattr(ocr.settings, "ocr_preprocess_images", False)

    image = Image.new("RGB", (100, 50), color="white")

    assert ocr.preprocess_image_for_ocr(image) is image
