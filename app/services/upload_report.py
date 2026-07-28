import base64
import json


def encode_upload_report(results: list[dict]) -> str:
    payload = json.dumps(results, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_upload_report(value: str | None) -> list[dict]:
    if not value:
        return []

    try:
        payload = base64.urlsafe_b64decode(value.encode("ascii"))
        results = json.loads(payload.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return []

    if not isinstance(results, list):
        return []

    cleaned = []
    for item in results:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "filename": str(item.get("filename") or "Unknown file"),
                "status": str(item.get("status") or "error"),
                "message": str(item.get("message") or ""),
                "document_id": item.get("document_id"),
                "size": item.get("size"),
                "reason": str(item.get("reason") or ""),
                "suggestions": [
                    str(suggestion)
                    for suggestion in item.get("suggestions", [])
                    if str(suggestion).strip()
                ]
                if isinstance(item.get("suggestions"), list)
                else [],
            }
        )

    return cleaned


def summarize_upload_report(results: list[dict]) -> dict:
    successful = sum(1 for item in results if item.get("status") == "success")
    failed = sum(1 for item in results if item.get("status") == "error")
    needs_ocr = sum(1 for item in results if item.get("status") == "needs_ocr")
    queued = sum(1 for item in results if item.get("status") == "queued")

    return {
        "results": results,
        "successful": successful,
        "failed": failed,
        "needs_ocr": needs_ocr,
        "queued": queued,
        "total": len(results),
    }
