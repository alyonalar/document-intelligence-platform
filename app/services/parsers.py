from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "tiff"}


def parse_txt(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8", errors="ignore").strip()


def parse_md(file_path: str) -> str:
    return Path(file_path).read_text(encoding="utf-8", errors="ignore").strip()


def parse_docx(file_path: str) -> str:
    doc = DocxDocument(file_path)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def parse_pdf(file_path: str) -> str:
    return "\n\n".join(item["text"] for item in parse_pdf_pages(file_path)).strip()


def parse_pdf_pages(file_path: str) -> list[dict]:
    reader = PdfReader(file_path)
    pages = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page_number": index, "text": text.strip()})

    return pages


def extract_text_by_extension(file_path: str, extension: str) -> str:
    extension = extension.lower()

    if extension == "txt":
        return parse_txt(file_path)
    if extension == "md":
        return parse_md(file_path)
    if extension == "docx":
        return parse_docx(file_path)
    if extension == "pdf":
        return parse_pdf(file_path)
    if extension in IMAGE_EXTENSIONS:
        return ""

    raise ValueError(f"Unsupported extension: {extension}")
