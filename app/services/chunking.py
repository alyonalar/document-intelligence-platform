import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = end - overlap

    return chunks


def chunk_text_records(text: str, chunk_size: int = 800, overlap: int = 120) -> list[dict]:
    return [
        {
            "chunk_id": index,
            "id": index,
            "text": chunk,
        }
        for index, chunk in enumerate(
            chunk_text(text, chunk_size=chunk_size, overlap=overlap),
            start=1,
        )
    ]


def chunk_pages(
    pages: list[dict],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[dict]:
    records = []
    chunk_id = 1

    for page in pages:
        for chunk in chunk_text(page.get("text", ""), chunk_size=chunk_size, overlap=overlap):
            records.append(
                {
                    "chunk_id": chunk_id,
                    "id": chunk_id,
                    "page_number": page.get("page_number"),
                    "text": chunk,
                }
            )
            chunk_id += 1

    return records
