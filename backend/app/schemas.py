from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums import ParseStatus, ResultDecision, ReviewStatus, TaskStatus


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class CreateTaskResponse(BaseModel):
    task_id: UUID
    title: str
    raw_query: str
    status: TaskStatus
    progress_percent: int
    events_url: str
    results_url: str


class CreateScreeningTaskRequest(BaseModel):
    query: str
    title: str | None = None


class CreateContractImportResponse(BaseModel):
    import_id: UUID
    title: str
    status: TaskStatus
    progress_percent: int
    file_count: int


class ContractLibraryItem(BaseModel):
    contract_id: UUID
    file_name: str
    parse_status: ParseStatus
    file_size_bytes: int
    page_count: int | None = None
    import_id: UUID
    created_at: datetime


class TaskCounts(BaseModel):
    documents: int
    included: int
    uncertain: int
    excluded: int


class ReviewCounts(BaseModel):
    unreviewed: int
    reviewed: int


class TaskSummaryResponse(BaseModel):
    task_id: UUID
    title: str
    raw_query: str
    status: TaskStatus
    progress_percent: int
    current_stage: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    counts: TaskCounts


class TaskListItem(BaseModel):
    task_id: UUID
    title: str
    raw_query: str
    status: TaskStatus
    progress_percent: int
    current_stage: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    counts: TaskCounts
    review_counts: ReviewCounts


class TaskListResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    limit: int
    offset: int


class EvidenceItem(BaseModel):
    page: int | None = None
    text: str
    source: Literal["qmd"] = "qmd"
    score: float | None = None
    condition_id: str
    artifact_ref: str | None = None


class DocumentResultItem(BaseModel):
    result_id: UUID
    document_uri: str
    document_path: str
    document_title: str | None = None
    collection: str
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float
    review_status: ReviewStatus = ReviewStatus.unreviewed
    review_decision: ResultDecision | None = None
    review_note: str | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReviewResultRequest(BaseModel):
    review_status: Literal["reviewed"]
    review_decision: ResultDecision
    review_note: str | None = None
    reviewer_name: str = Field(min_length=1, max_length=128)

    @field_validator("reviewer_name")
    @classmethod
    def normalize_reviewer_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reviewer_name is required")
        return value


class ReviewResultResponse(BaseModel):
    result: DocumentResultItem


class ResultBuckets(BaseModel):
    included: list[DocumentResultItem]
    uncertain: list[DocumentResultItem]
    excluded: list[DocumentResultItem]


class TaskResultsResponse(BaseModel):
    task_id: UUID
    buckets: ResultBuckets


class StreamEventEnvelope(BaseModel):
    event_id: str
    type: str
    task_id: UUID
    timestamp: datetime
    payload: dict[str, Any]


class ScreeningCondition(BaseModel):
    id: str
    description: str
    operator: Literal["semantic_match"]
    value: str
    qmd_queries: list[str]
    evidence_required: int = 1
    structured: bool


class ScreeningPlanPayload(BaseModel):
    target: Literal["qmd_document"] = "qmd_document"
    conditions: list[ScreeningCondition]
    decision_policy: Literal[
        "phase1_keyword_candidate_uncertain_on_structured_comparison"
    ] = "phase1_keyword_candidate_uncertain_on_structured_comparison"


class ContractScreeningDecision(BaseModel):
    contract_id: UUID
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float
