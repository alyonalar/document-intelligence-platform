from app.services.upload_guidance import build_upload_guidance


def test_upload_guidance_explains_unsupported_type():
    guidance = build_upload_guidance("Unsupported file type: sample.exe")

    assert guidance["reason"] == "This extension is not enabled for uploads."
    assert any("supported formats" in item for item in guidance["suggestions"])


def test_upload_guidance_explains_ocr_disabled():
    guidance = build_upload_guidance(
        "No readable text was extracted. OCR is disabled.",
        status="needs_ocr",
        filename="scan.pdf",
        file_type="pdf",
    )

    assert "likely needs OCR" in guidance["reason"]
    assert any("OCR_ENABLED=true" in item for item in guidance["suggestions"])


def test_upload_guidance_explains_fake_pdf():
    guidance = build_upload_guidance("File does not look like a valid PDF: fake.pdf")

    assert "not a real PDF" in guidance["reason"]
    assert any("renaming the extension" in item for item in guidance["suggestions"])
