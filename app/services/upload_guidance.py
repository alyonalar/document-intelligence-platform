from app.core.config import settings


def build_upload_guidance(
    message: str,
    status: str = "error",
    filename: str = "",
    file_type: str = "",
) -> dict:
    text = f"{message} {filename} {file_type}".lower()
    reason = "The app could not process this file."
    suggestions = [
        "Check that the file opens locally and try uploading it again.",
    ]

    if status == "queued":
        return {
            "reason": "The file was accepted and is waiting for background processing.",
            "suggestions": [
                "Run the worker with `python -m app.worker` if processing does not start.",
                "Refresh the page or open the document to watch the processing status.",
            ],
        }

    if status == "success":
        return {
            "reason": "The file was uploaded, parsed, and indexed successfully.",
            "suggestions": [
                "Open the document to review extracted text, sources, dates, and action items.",
            ],
        }

    if "ocr is disabled" in text or status == "needs_ocr":
        reason = "No readable text was extracted; this file likely needs OCR."
        suggestions = [
            "Install Tesseract and set OCR_ENABLED=true in `.env`.",
            "For scanned PDFs on Windows, install Poppler as well.",
            "Retry processing after OCR dependencies are configured.",
        ]
    elif "unsupported file type" in text or "only prepared" in text:
        reason = "This extension is not enabled for uploads."
        suggestions = [
            f"Upload one of the supported formats: {', '.join(sorted(settings.allowed_extensions_set))}.",
            "Convert the file to PDF, DOCX, TXT, Markdown, PNG, JPG, JPEG, or TIFF and try again.",
        ]
    elif "too large" in text:
        reason = "The file is larger than the configured upload limit."
        suggestions = [
            f"Keep files under {settings.max_file_size_mb} MB or raise MAX_FILE_SIZE_MB in `.env`.",
            "Split large PDFs or export only the pages you need to analyze.",
        ]
    elif "empty" in text:
        reason = "The uploaded file has no bytes."
        suggestions = [
            "Export or save the source document again, then retry the upload.",
            "If this is a scan, upload the actual image/PDF file instead of an empty placeholder.",
        ]
    elif "valid pdf" in text:
        reason = "The extension is `.pdf`, but the file signature is not a real PDF."
        suggestions = [
            "Export the source file as PDF again instead of renaming the extension.",
            "Open the file locally; if it fails to open, repair or regenerate it before uploading.",
        ]
    elif "valid docx" in text:
        reason = "The extension is `.docx`, but the file is not a valid DOCX package."
        suggestions = [
            "Open the document in Word or LibreOffice and save it again as `.docx`.",
            "Avoid uploading legacy `.doc` files until a DOC parser is added.",
        ]
    elif "text document" in text:
        reason = "The file looks binary, but it was uploaded as text or Markdown."
        suggestions = [
            "Save the content as UTF-8 `.txt` or `.md` and retry.",
            "If this is a PDF, image, or DOCX, upload it with the correct extension.",
        ]
    elif "valid png" in text or "valid jpeg" in text or "valid tiff" in text:
        reason = "The image extension and file signature do not match."
        suggestions = [
            "Export the image again in the matching format.",
            "Do not fix image type issues by renaming the file extension only.",
        ]
    elif "missing ocr python packages" in text:
        reason = "OCR is enabled, but required Python packages are missing."
        suggestions = [
            "Install project dependencies from `requirements.txt` in the active virtual environment.",
            "Retry processing after `pdf2image`, `pytesseract`, and `Pillow` are available.",
        ]
    elif "tesseract command was not found" in text:
        reason = "OCR is enabled, but the Tesseract executable was not found."
        suggestions = [
            "Install Tesseract or set TESSERACT_CMD to the full executable path.",
            "Restart the app after changing OCR configuration.",
        ]
    elif "stored file is missing" in text:
        reason = "The database record exists, but the saved upload file is missing."
        suggestions = [
            "Upload the document again so the parser can read the source file.",
            "Avoid deleting files from the upload directory while records still exist.",
        ]

    return {
        "reason": reason,
        "suggestions": suggestions,
    }
