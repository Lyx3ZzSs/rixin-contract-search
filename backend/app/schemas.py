from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums import (
    ConditionOperator,
    ConditionType,
    ConditionVerdictValue,
    EvidenceRole,
    EvidenceSourceTool,
    ParseStatus,
    ResultDecision,
    ReviewStatus,
    TaskStatus,
    UncertainReason,
    VerificationStatus,
    VerificationStrategy,
)


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
    decision_basis: dict[str, Any] = Field(default_factory=dict)
    uncertain_reasons: list[UncertainReason] = Field(default_factory=list)
    evidence_support_rate: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.query_only
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
    operator: ConditionOperator = ConditionOperator.semantic_match
    value: str | int | float | bool | dict[str, Any] | list[Any]
    qmd_queries: list[str]
    evidence_required: int = 1
    structured: bool
    condition_type: ConditionType = ConditionType.semantic_risk
    normalization_hint: dict[str, Any] = Field(default_factory=dict)
    verification_strategy: VerificationStrategy = VerificationStrategy.query_only
    required_evidence_count: int = 1
    negative_evidence_allowed: bool = False


class ScreeningPlanPayload(BaseModel):
    target: Literal["qmd_document"] = "qmd_document"
    plan_version: int = 1
    conditions: list[ScreeningCondition] = Field(min_length=1)
    decision_policy: Literal[
        "phase1_keyword_candidate_uncertain_on_structured_comparison",
        "all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
    ] = "phase1_keyword_candidate_uncertain_on_structured_comparison"


class ContractScreeningDecision(BaseModel):
    contract_id: UUID
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float


class LedgerEvidenceItem(EvidenceItem):
    role: EvidenceRole = EvidenceRole.retrieval_candidate
    source_tool: EvidenceSourceTool = EvidenceSourceTool.query
    document_uri: str | None = None
    document_path: str | None = None
    collection: str | None = None
    anchor: str | None = None
    context: str | None = None
    used_for_decision: bool = False


class ConditionVerdictItem(BaseModel):
    verdict_id: UUID
    task_id: UUID
    document_uri: str
    condition_id: str
    verdict: ConditionVerdictValue
    confidence: float
    supporting_evidence: list[LedgerEvidenceItem]
    contradicting_evidence: list[LedgerEvidenceItem]
    missing_reason: str | None = None
    verification_method: VerificationStrategy
    created_at: datetime


class ConditionVerdictResponse(BaseModel):
    task_id: UUID
    items: list[ConditionVerdictItem]


class EvidenceLedgerResponse(BaseModel):
    task_id: UUID
    items: list[LedgerEvidenceItem]


class QmdDocumentPreviewResponse(BaseModel):
    document_uri: str
    document_title: str | None = None
    collection: str | None = None
    toc: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    can_open: bool = False
    can_download: bool = False


class QmdEvidenceContextResponse(BaseModel):
    document_uri: str
    condition_id: str | None = None
    page: int | None = None
    anchor: str | None = None
    text: str
    source_tool: EvidenceSourceTool


class AgentEvalMetrics(BaseModel):
    precision: float
    recall: float
    uncertain_rate: float
    evidence_support_rate: float
    schema_failure_rate: float
    verification_failure_rate: float
