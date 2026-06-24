from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, GUID, utcnow
from app.enums import ParseStatus, TaskStatus, VerificationStatus


class ScreeningTask(Base):
    __tablename__ = "screening_tasks"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.uploaded.value)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default=TaskStatus.uploaded.value)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    files = relationship("ContractFile", back_populates="task", cascade="all, delete-orphan")
    plan = relationship("ScreeningPlan", back_populates="task", cascade="all, delete-orphan", uselist=False)
    results = relationship("ContractScreeningResult", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_screening_tasks_owner_created", "owner_id", "created_at"),
        Index("ix_screening_tasks_owner_id", "owner_id", "id"),
        Index("ix_screening_tasks_status_created", "status", "created_at"),
    )


class ContractFile(Base):
    __tablename__ = "contract_files"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default=ParseStatus.pending.value)
    parse_quality: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    task = relationship("ScreeningTask", back_populates="files")
    artifacts = relationship("ParsedArtifact", back_populates="contract", cascade="all, delete-orphan")
    results = relationship("ContractScreeningResult", back_populates="contract", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contract_files_task", "task_id"),
        Index("ix_contract_files_owner_id", "owner_id", "id"),
        Index("ix_contract_files_sha256", "sha256"),
    )


class ParsedArtifact(Base):
    __tablename__ = "parsed_artifacts"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    contract_id: Mapped[object] = mapped_column(GUID(), ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    contract = relationship("ContractFile", back_populates="artifacts")

    __table_args__ = (UniqueConstraint("contract_id", "artifact_type", "page_number", name="uq_parsed_artifacts_contract_type_page"),)


class ScreeningPlan(Base):
    __tablename__ = "screening_plans"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    task = relationship("ScreeningTask", back_populates="plan")


class QmdCandidateSnippet(Base):
    __tablename__ = "qmd_candidate_snippets"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    contract_id: Mapped[object | None] = mapped_column(GUID(), ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=True)
    document_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    condition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    snippet_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    qmd_docid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_weak: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_qmd_candidates_task_condition", "task_id", "condition_id"),)


class ScreeningDocumentResult(Base):
    __tablename__ = "screening_document_results"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    document_uri: Mapped[str] = mapped_column(Text, nullable=False)
    document_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    matched_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False)
    decision_basis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    uncertain_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_support_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default=VerificationStatus.query_only.value)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    review_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    task = relationship("ScreeningTask")

    __table_args__ = (
        UniqueConstraint("task_id", "document_uri", name="uq_document_results_task_document"),
        Index("ix_document_results_task_decision", "task_id", "decision"),
        Index("ix_document_results_task_review", "task_id", "review_status"),
    )


class ConditionVerdict(Base):
    __tablename__ = "condition_verdicts"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    document_uri: Mapped[str] = mapped_column(Text, nullable=False)
    condition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    supporting_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contradicting_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_method: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "document_uri", "condition_id", name="uq_condition_verdict_task_doc_condition"),
        Index("ix_condition_verdicts_task_document", "task_id", "document_uri"),
    )


class AgentEvalCase(Base):
    __tablename__ = "agent_eval_cases"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AgentEvalRun(Base):
    __tablename__ = "agent_eval_runs"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    case_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ContractScreeningResult(Base):
    __tablename__ = "contract_screening_results"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    contract_id: Mapped[object] = mapped_column(GUID(), ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    matched_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    task = relationship("ScreeningTask", back_populates="results")
    contract = relationship("ContractFile", back_populates="results")

    __table_args__ = (
        UniqueConstraint("task_id", "contract_id", name="uq_results_task_contract"),
        Index("ix_results_task_decision", "task_id", "decision"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object | None] = mapped_column(GUID(), nullable=True)
    contract_id: Mapped[object | None] = mapped_column(GUID(), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (Index("ix_audit_events_task_created", "task_id", "created_at"),)


class StreamEvent(Base):
    __tablename__ = "stream_events"

    id: Mapped[object] = mapped_column(GUID(), primary_key=True, default=uuid4)
    task_id: Mapped[object] = mapped_column(GUID(), ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="uq_stream_events_task_sequence"),
        Index("ix_stream_events_task_sequence", "task_id", "sequence"),
    )
