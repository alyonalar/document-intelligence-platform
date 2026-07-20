import importlib.util
import shutil
from pathlib import Path

from app.core.config import settings

IMAGE_OCR_EXTENSIONS = {"png", "jpg", "jpeg", "tiff"}
SUPPORTED_OCR_EXTENSIONS = {"pdf", *IMAGE_OCR_EXTENSIONS}
REQUIRED_PYTHON_PACKAGES = ("pdf2image", "pytesseract", "PIL")


class OCRUnavailableError(RuntimeError):
    pass


def package_available(package_name: str) -> bool:
    return importlib.util.find_spec(package_name) is not None


def missing_python_packages() -> list[str]:
    return [
        package_name
        for package_name in REQUIRED_PYTHON_PACKAGES
        if not package_available(package_name)
    ]


def tesseract_command_found() -> bool:
    return bool(shutil.which(settings.tesseract_cmd))


def ocr_available() -> bool:
    return bool(
        settings.ocr_enabled
        and settings.ocr_engine == "tesseract"
        and tesseract_command_found()
        and not missing_python_packages()
    )


def ocr_status() -> dict:
    missing_packages = missing_python_packages()

    return {
        "enabled": settings.ocr_enabled,
        "engine": settings.ocr_engine,
        "language": settings.ocr_language,
        "command": settings.tesseract_cmd,
        "command_found": tesseract_command_found(),
        "missing_python_packages": missing_packages,
        "dpi": settings.ocr_dpi,
        "max_pages": settings.ocr_max_pages,
        "preprocess_images": settings.ocr_preprocess_images,
        "image_target_width": settings.ocr_image_target_width,
        "contrast_factor": settings.ocr_contrast_factor,
        "available": ocr_available(),
    }


def explain_ocr_unavailable(extension: str) -> str:
    if extension not in SUPPORTED_OCR_EXTENSIONS:
        return f"OCR is only prepared for {', '.join(sorted(SUPPORTED_OCR_EXTENSIONS))} files."

    if not settings.ocr_enabled:
        return "OCR is disabled. Set OCR_ENABLED=true after installing an OCR engine."

    if settings.ocr_engine != "tesseract":
        return f"Unsupported OCR engine: {settings.ocr_engine}."

    missing_packages = missing_python_packages()
    if missing_packages:
        return "Missing OCR Python packages: " + ", ".join(missing_packages) + "."

    if not tesseract_command_found():
        return f"Tesseract command was not found: {settings.tesseract_cmd}."

    return "OCR adapter is configured, but OCR extraction failed."


def extract_pdf_text_with_tesseract(file_path: str) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:
        raise OCRUnavailableError(explain_ocr_unavailable("pdf")) from e

    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    try:
        images = convert_from_path(
            file_path,
            dpi=settings.ocr_dpi,
            first_page=1,
            last_page=max(1, settings.ocr_max_pages),
        )
    except Exception as e:
        raise OCRUnavailableError(f"Failed to render PDF pages for OCR: {e}") from e

    page_texts = []
    for image in images:
        try:
            text = pytesseract.image_to_string(image, lang=settings.ocr_language)
        except Exception as e:
            raise OCRUnavailableError(f"Tesseract failed to extract text: {e}") from e

        if text.strip():
            page_texts.append(text.strip())

    return "\n\n".join(page_texts).strip()


def preprocess_image_for_ocr(image):
    if not settings.ocr_preprocess_images:
        return image

    from PIL import ImageEnhance

    processed = image.convert("L")

    if settings.ocr_contrast_factor and settings.ocr_contrast_factor != 1:
        processed = ImageEnhance.Contrast(processed).enhance(settings.ocr_contrast_factor)

    target_width = settings.ocr_image_target_width
    if target_width and processed.width < target_width:
        ratio = target_width / processed.width
        target_height = max(1, int(processed.height * ratio))
        processed = processed.resize((target_width, target_height))

    return processed


def extract_image_text_with_tesseract(file_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise OCRUnavailableError(explain_ocr_unavailable("png")) from e

    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    try:
        with Image.open(file_path) as image:
            processed_image = preprocess_image_for_ocr(image)
            text = pytesseract.image_to_string(processed_image, lang=settings.ocr_language)
    except Exception as e:
        raise OCRUnavailableError(f"Tesseract failed to extract text from image: {e}") from e

    return text.strip()


def extract_text_with_ocr(file_path: str, extension: str) -> str:
    extension = extension.lower()
    if extension not in SUPPORTED_OCR_EXTENSIONS:
        raise OCRUnavailableError(explain_ocr_unavailable(extension))

    if not Path(file_path).exists():
        raise OCRUnavailableError(
            "Stored file is missing. Upload the document again before retrying."
        )

    if not ocr_available():
        raise OCRUnavailableError(explain_ocr_unavailable(extension))

    if extension == "pdf":
        text = extract_pdf_text_with_tesseract(file_path)
        if text:
            return text
        raise OCRUnavailableError("OCR completed, but no readable text was extracted.")

    if extension in IMAGE_OCR_EXTENSIONS:
        text = extract_image_text_with_tesseract(file_path)
        if text:
            return text
        raise OCRUnavailableError(
            "OCR completed, but no readable text was extracted from the image."
        )

    raise OCRUnavailableError(explain_ocr_unavailable(extension))
