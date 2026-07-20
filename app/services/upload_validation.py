from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings

TEXT_EXTENSIONS = {"txt", "md"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "tiff"}
PDF_SIGNATURE = b"%PDF"
ZIP_SIGNATURE = b"PK"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
TIFF_SIGNATURES = (b"II*\x00", b"MM\x00*")


def safe_original_filename(filename: str) -> str:
    return Path(filename).name.strip()


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def get_upload_size(file: UploadFile) -> int:
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    return size


def read_prefix(file: UploadFile, size: int = 2048) -> bytes:
    prefix = file.file.read(size)
    file.file.seek(0)
    return prefix


def validate_upload_file(file: UploadFile) -> tuple[str, str, int]:
    if not file.filename:
        raise ValueError("File must have a name.")

    original_filename = safe_original_filename(file.filename)
    if not original_filename:
        raise ValueError("File must have a name.")

    extension = get_extension(original_filename)
    if extension not in settings.allowed_extensions_set:
        raise ValueError(f"Unsupported file type: {original_filename}")

    size = get_upload_size(file)
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    if size > max_size_bytes:
        raise ValueError(
            f"File is too large: {original_filename}. Max size is {settings.max_file_size_mb} MB."
        )

    if size == 0:
        raise ValueError(f"File is empty: {original_filename}")

    validate_file_signature(file, extension, original_filename)

    return original_filename, extension, size


def validate_file_signature(file: UploadFile, extension: str, filename: str) -> None:
    prefix = read_prefix(file)

    if extension == "pdf" and not prefix.startswith(PDF_SIGNATURE):
        raise ValueError(f"File does not look like a valid PDF: {filename}")

    if extension == "docx" and not prefix.startswith(ZIP_SIGNATURE):
        raise ValueError(f"File does not look like a valid DOCX: {filename}")

    if extension in TEXT_EXTENSIONS and b"\x00" in prefix:
        raise ValueError(f"File does not look like a text document: {filename}")

    if extension == "png" and not prefix.startswith(PNG_SIGNATURE):
        raise ValueError(f"File does not look like a valid PNG image: {filename}")

    if extension in {"jpg", "jpeg"} and not prefix.startswith(JPEG_SIGNATURE):
        raise ValueError(f"File does not look like a valid JPEG image: {filename}")

    if extension == "tiff" and not prefix.startswith(TIFF_SIGNATURES):
        raise ValueError(f"File does not look like a valid TIFF image: {filename}")
