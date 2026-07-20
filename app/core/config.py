from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Document Intelligence Platform"
    database_url: str = "sqlite:///data/app.db"
    upload_dir: str = "data/uploads"
    allowed_extensions: str = "txt,docx,md,pdf,png,jpg,jpeg,tiff"

    debug: bool = False
    max_file_size_mb: int = 20

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_enabled: bool = False
    semantic_search_enabled: bool = False
    chroma_dir: str = "data/chroma"
    ocr_enabled: bool = False
    ocr_engine: str = "tesseract"
    ocr_language: str = "eng+rus"
    tesseract_cmd: str = "tesseract"
    ocr_dpi: int = 200
    ocr_max_pages: int = 5
    ocr_preprocess_images: bool = True
    ocr_image_target_width: int = 1800
    ocr_contrast_factor: float = 1.6
    processing_mode: str = "sync"
    processing_max_attempts: int = 3
    processing_stale_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.allowed_extensions.split(",") if ext.strip()}

    @field_validator("processing_mode")
    @classmethod
    def normalize_processing_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"sync", "queued"}:
            raise ValueError("PROCESSING_MODE must be either 'sync' or 'queued'")
        return normalized


settings = Settings()
