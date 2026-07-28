from app.db.models import Document

STATUS_DETAILS = {
    "uploaded": {
        "label": "Uploaded",
        "description": "File is stored and waiting for processing.",
        "progress": 20,
        "active_step": "uploaded",
    },
    "queued": {
        "label": "Queued for worker",
        "description": "Processing is queued and will start when the worker picks it up.",
        "progress": 30,
        "active_step": "queued",
    },
    "parsing": {
        "label": "Extracting text",
        "description": "The parser is extracting readable text and metadata.",
        "progress": 50,
        "active_step": "parsing",
    },
    "indexing": {
        "label": "Indexing sources",
        "description": "Chunks and retrieval metadata are being prepared.",
        "progress": 75,
        "active_step": "indexing",
    },
    "ready": {
        "label": "Ready for questions",
        "description": "The document is processed and ready for search, QA, export, and comparison.",
        "progress": 100,
        "active_step": "ready",
    },
    "needs_ocr": {
        "label": "Needs OCR",
        "description": "No readable text was extracted. Enable OCR or retry with OCR dependencies configured.",
        "progress": 45,
        "active_step": "needs_ocr",
    },
    "failed": {
        "label": "Processing failed",
        "description": "Processing stopped with an error. Review the error and retry after fixing the cause.",
        "progress": 45,
        "active_step": "failed",
    },
}

BASE_STEPS = [
    ("uploaded", "Uploaded"),
    ("queued", "Queued"),
    ("parsing", "Parsing"),
    ("indexing", "Indexing"),
    ("ready", "Ready"),
]

STEP_ORDER = {key: index for index, (key, _) in enumerate(BASE_STEPS)}


def build_processing_pipeline(document: Document) -> dict:
    status = document.processing_status or "uploaded"
    details = STATUS_DETAILS.get(
        status,
        {
            "label": status.replace("_", " ").title(),
            "description": "Document status is being tracked.",
            "progress": 0,
            "active_step": status,
        },
    )
    active_step = details["active_step"]

    steps = []
    active_index = STEP_ORDER.get(active_step, 0)
    for key, label in BASE_STEPS:
        state = "pending"
        if status == "ready" or STEP_ORDER[key] < active_index:
            state = "complete"
        elif key == active_step:
            state = "active"

        steps.append({"key": key, "label": label, "state": state})

    if status in {"needs_ocr", "failed"}:
        steps[-1] = {
            "key": status,
            "label": details["label"],
            "state": "blocked",
        }

    return {
        "status": status,
        "label": details["label"],
        "description": details["description"],
        "progress": details["progress"],
        "steps": steps,
        "indexed_chunks": document.indexed_chunks or 0,
        "error": document.processing_error,
    }
