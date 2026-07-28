from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class CollectionDocumentLink(SQLModel, table=True):
    collection_id: int | None = Field(
        default=None,
        foreign_key="collection.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    document_id: int | None = Field(
        default=None,
        foreign_key="document.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    created_at: datetime = Field(default_factory=utc_now)


class Collection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    stored_path: str
    file_type: str
    file_size: int
    title: str | None = None
    raw_text: str | None = None

    word_count: int = 0
    estimated_reading_time_min: int = 0
    summary_short: str | None = None
    key_points: str | None = None
    bullet_summary: str | None = None
    keywords: str | None = None
    document_type: str | None = None
    detected_dates: str | None = None
    action_items: str | None = None
    suggested_questions: str | None = None
    llm_summary: str | None = None
    category: str | None = None
    processing_status: str = Field(default="ready")
    processing_error: str | None = None
    intelligence_status: str = Field(default="pending")
    intelligence_error: str | None = None
    intelligence_processed_at: datetime | None = None
    indexed_chunks: int = 0

    created_at: datetime = Field(default_factory=utc_now)


class ProcessingJob(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_type: str
    status: str = Field(default="queued")
    document_id: int | None = Field(
        default=None,
        foreign_key="document.id",
        ondelete="CASCADE",
    )
    message: str | None = None
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ActionItemState(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    action_key: str = Field(index=True, unique=True)
    status: str = Field(default="done")
    note: str | None = None
    due_date_override: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class QAInteraction(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    scope: str
    question: str
    answer: str
    document_ids: str | None = None
    model: str | None = None
    retrieval: str | None = None
    sources: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DocumentEntity(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    entity_type: str = Field(index=True)
    value: str
    normalized_value: str | None = Field(default=None, index=True)
    source_text: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DocumentRelation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_document_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    target_document_id: int | None = Field(
        default=None,
        foreign_key="document.id",
        ondelete="CASCADE",
        index=True,
    )
    source_entity_id: int | None = Field(
        default=None,
        foreign_key="documententity.id",
        ondelete="CASCADE",
        index=True,
    )
    target_entity_id: int | None = Field(
        default=None,
        foreign_key="documententity.id",
        ondelete="CASCADE",
        index=True,
    )
    relation_type: str = Field(index=True)
    evidence_text: str | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DocumentObligation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    subject: str
    action: str
    object: str | None = None
    due_date: datetime | None = Field(default=None, index=True)
    due_date_text: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str = Field(default="open", index=True)
    source_text: str
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentRisk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    risk_type: str = Field(index=True)
    title: str
    description: str
    severity: str = Field(index=True)
    source_text: str
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utc_now)


class EntityAlias(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    entity_type: str = Field(index=True)
    canonical_value: str = Field(index=True)
    alias_value: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
