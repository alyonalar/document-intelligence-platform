from app.services.upload_report import (
    decode_upload_report,
    encode_upload_report,
    summarize_upload_report,
)


def test_upload_report_round_trips_results():
    results = [
        {
            "filename": "ok.txt",
            "status": "success",
            "message": "Uploaded.",
            "document_id": 1,
            "size": 12,
        },
        {
            "filename": "bad.exe",
            "status": "error",
            "message": "Unsupported file type.",
            "reason": "This extension is not enabled.",
            "suggestions": ["Upload a supported format."],
        },
    ]

    encoded = encode_upload_report(results)
    decoded = decode_upload_report(encoded)

    assert decoded[0] == {
        **results[0],
        "reason": "",
        "suggestions": [],
    }
    assert decoded[1] == {
        "filename": "bad.exe",
        "status": "error",
        "message": "Unsupported file type.",
        "document_id": None,
        "size": None,
        "reason": "This extension is not enabled.",
        "suggestions": ["Upload a supported format."],
    }


def test_upload_report_ignores_invalid_payload():
    assert decode_upload_report("not-base64") == []


def test_summarize_upload_report_counts_statuses():
    summary = summarize_upload_report(
        [
            {"status": "success"},
            {"status": "error"},
            {"status": "needs_ocr"},
            {"status": "queued"},
            {"status": "success"},
        ]
    )

    assert summary["successful"] == 2
    assert summary["failed"] == 1
    assert summary["needs_ocr"] == 1
    assert summary["queued"] == 1
    assert summary["total"] == 5
