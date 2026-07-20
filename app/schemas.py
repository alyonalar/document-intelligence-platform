from datetime import datetime

from pydantic import BaseModel, Field


class DocumentListItem(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    word_count: int
    estimated_reading_time_min: int
    category: str | None = None
    summary_short: str | None = None
    keywords: str | None = None
    document_type: str | None = None
    detected_dates: str | None = None
    action_items: str | None = None
    suggested_questions: str | None = None
    processing_status: str = "ready"
    processing_label: str = "Ready for questions"
    processing_progress: int = 100
    processing_error: str | None = None
    indexed_chunks: int = 0


class DocumentSearchResponse(BaseModel):
    query: str = ""
    total: int
    documents: list[DocumentListItem]


class ProcessingJobItem(BaseModel):
    id: int
    job_type: str
    status: str
    document_id: int | None = None
    message: str | None = None
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ProcessingJobListResponse(BaseModel):
    total: int
    jobs: list[ProcessingJobItem]


class DocumentStructure(BaseModel):
    estimated_pages: int
    sections: list[str] = Field(default_factory=list)
    preview_blocks: list[str] = Field(default_factory=list)


class DocumentDetailResponse(DocumentListItem):
    raw_text: str | None = None
    llm_summary: str | None = None
    structure: DocumentStructure


class AskDocumentRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: str = Field(default="local", pattern="^(local|llm)$")


class AskWorkspaceRequest(BaseModel):
    question: str = Field(..., min_length=1)
    document_ids: list[int] = Field(default_factory=list)


class CompareDocumentsRequest(BaseModel):
    document_ids: list[int] = Field(..., min_length=2, max_length=2)


class DocumentDiffResponse(BaseModel):
    doc1_name: str
    doc2_name: str
    word_count_delta: int
    keyword_similarity: float
    common_keywords: list[str]
    only_in_doc1_keywords: list[str]
    only_in_doc2_keywords: list[str]
    doc1_sections: list[str]
    doc2_sections: list[str]
    doc1_preview: list[str]
    doc2_preview: list[str]


class CompareDocumentsResponse(BaseModel):
    diff: DocumentDiffResponse
    llm_answer: str | None = None
    model: str | None = None


class SourceItem(BaseModel):
    document_id: int | None = None
    filename: str | None = None
    chunk_id: int | None = None
    page_number: int | None = None
    text: str
    score: float | int | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str | None = None
    retrieval: str | None = None
    sources: list[SourceItem | str] = Field(default_factory=list)


class ActionStatsResponse(BaseModel):
    total: int
    overdue: int
    upcoming: int
    no_date: int
    due_soon: int
    done: int
    open: int


class ActionItemResponse(BaseModel):
    id: str
    text: str
    document_id: int
    filename: str
    title: str
    document_type: str
    dates: list[str] = Field(default_factory=list)
    due_date: str | None = None
    due_date_override: str | None = None
    due_date_source: str
    due_label: str
    timing_status: str
    days_until: int | None = None
    context: str
    action_key: str
    completed: bool
    completion_status: str
    note: str = ""
    source_chunk_id: int | None = None
    source_anchor: str = "#extracted-text"
    created_at: str


class ActionListResponse(BaseModel):
    query: str = ""
    total: int
    stats: ActionStatsResponse
    actions: list[ActionItemResponse]


class ActionStatusUpdateResponse(BaseModel):
    action_key: str
    status: str
    stored_status: str


class ActionNoteUpdateResponse(BaseModel):
    action_key: str
    note: str = ""
    due_date_override: str | None = None
    status: str


class DocumentInsightsResponse(BaseModel):
    success: bool
    message: str
    document_type: str | None = None
    dates: int = 0
    actions: int = 0
    questions: int = 0


class BulkDocumentInsightsResponse(BaseModel):
    updated: int
    skipped: int


class IntelligenceRecomputeResponse(BaseModel):
    success: bool = True
    message: str = ""
    entities: int = 0
    relations: int = 0
    obligations: int = 0
    risks: int = 0


class BulkIntelligenceRecomputeResponse(BaseModel):
    processed: int
    errors: int
    total: int


class DocumentEntityResponse(BaseModel):
    id: int
    document_id: int
    entity_type: str
    value: str
    normalized_value: str | None = None
    source_text: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime


class DocumentRelationResponse(BaseModel):
    id: int
    source_document_id: int
    target_document_id: int | None = None
    source_entity_id: int | None = None
    target_entity_id: int | None = None
    relation_type: str
    evidence_text: str | None = None
    confidence: float | None = None
    created_at: datetime


class DocumentObligationResponse(BaseModel):
    id: int
    document_id: int
    subject: str
    action: str
    object: str | None = None
    due_date: datetime | None = None
    due_date_text: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str
    source_text: str
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class DocumentRiskResponse(BaseModel):
    id: int
    document_id: int
    risk_type: str
    title: str
    description: str
    severity: str
    source_text: str
    page_number: int | None = None
    chunk_index: int | None = None
    confidence: float | None = None
    created_at: datetime


class GraphNode(BaseModel):
    id: str
    type: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class IntelligenceSummaryResponse(BaseModel):
    total_entities: int
    total_relations: int
    open_obligations: int
    overdue_obligations: int
    high_risks: int
    documents_with_intelligence_errors: int
    top_organizations: list[dict]
    top_related_documents: list[dict]


class ObligationSummaryResponse(BaseModel):
    total: int
    open: int
    overdue: int
    due_soon: int
    no_due_date: int
    done: int
    dismissed: int


class RiskSummaryResponse(BaseModel):
    total: int
    high: int
    medium: int
    low: int
    by_type: dict
