# Phase 3 Trustworthy Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the qmd-first contract screening Agent so every result can be traced to condition-level verdicts, verified evidence, clear uncertainty reasons, and optional MinerU document preview.

**Architecture:** Keep Phase 2 APIs compatible and add Phase 3 as an evidence layer around the existing LangGraph Agent. qmd `query` remains candidate retrieval; new MinerU deep-read methods verify candidate documents per condition, persist `condition_verdicts`, enrich document results, expose ledger/preview APIs, and add a small evaluation harness.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, LangGraph, httpx MCP client, pytest, React, TypeScript, Vitest.

---

## File Structure

Backend model and schema changes:

- Modify `backend/app/enums.py`: add verdict, verification, evidence role/source, uncertainty, and document audit enum values.
- Modify `backend/app/schemas.py`: add ScreeningPlan v2-compatible fields, condition verdict schemas, evidence ledger schemas, qmd document preview schemas, eval schemas, and Phase 3 result fields.
- Modify `backend/app/models.py`: add `ConditionVerdict`, `AgentEvalCase`, `AgentEvalRun`; extend `ScreeningDocumentResult`.
- Create `backend/alembic/versions/0004_phase3_trustworthy_evidence.py`: migration for new tables and nullable Phase 3 columns.

Backend qmd, agent, API, and eval changes:

- Modify `backend/app/services/retrieval/qmd_client.py`: add `list_tools`, `doc_toc`, `doc_grep`, `doc_read`, `doc_query`, `doc_elements`, `document_preview`, and safe URI helpers.
- Create `backend/app/services/agent/verifier.py`: turn aggregated qmd candidates plus deep-read responses into condition verdict payloads.
- Modify `backend/app/services/agent/llm.py`: add plan v2 prompt schema and `judge_condition` method with validation/repair.
- Modify `backend/app/services/agent/langgraph_agent.py`: add verification node after retrieval and before document result persistence.
- Create `backend/app/services/agent/evidence_ledger.py`: read verdicts and document results into API/export-friendly ledger rows.
- Create `backend/app/services/evals.py`: compute precision, recall, uncertain rate, evidence support rate, schema failure rate, and verification failure rate.
- Modify `backend/app/services/exports.py`: append Phase 3 fields to CSV/XLSX/JSON exports without removing Phase 2 fields.
- Modify `backend/app/api/screening_tasks.py`: add condition verdict and evidence ledger endpoints.
- Create `backend/app/api/qmd_documents.py`: qmd document preview/context/open-link/download endpoints.
- Create `backend/app/api/agent_evals.py`: internal eval run endpoints.
- Modify `backend/app/main.py`: register new routers.

Backend tests:

- Create `backend/tests/test_phase3_plan_schema.py`
- Create `backend/tests/test_phase3_models_migration.py`
- Create `backend/tests/test_qmd_deep_read_client.py`
- Create `backend/tests/test_phase3_agent_verification.py`
- Create `backend/tests/test_phase3_evidence_api.py`
- Create `backend/tests/test_qmd_documents_api.py`
- Create `backend/tests/test_agent_evals.py`
- Modify `backend/tests/test_phase2_exports.py`

Frontend changes:

- Modify `frontend/src/lib/types.ts`: add condition verdict, ledger, preview, and eval types.
- Modify `frontend/src/lib/api.ts`: add Phase 3 API client functions.
- Modify `frontend/src/pages/TaskProgressPage.tsx`: load and render condition matrix, evidence ledger, uncertainty reasons, and preview context.
- Modify `frontend/src/lib/errorMessages.ts`: add new Phase 3 error messages.
- Modify `frontend/src/styles/contract-agent.css`: add compact matrix, ledger, and preview styles.
- Modify `frontend/tests/TaskProgressPage.test.tsx`
- Create `frontend/tests/phase3Api.test.ts`

Documentation:

- Modify `README.md`: add Phase 3 capability summary after Phase 2.
- Create `notes/phase-3-acceptance-checklist.md`

---

### Task 1: ScreeningPlan v2 And Phase 3 Schemas

**Files:**
- Modify: `backend/app/enums.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_phase3_plan_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `backend/tests/test_phase3_plan_schema.py`:

```python
from app.enums import ConditionVerdictValue, EvidenceRole, VerificationStatus
from app.schemas import ScreeningCondition, ScreeningPlanPayload


def test_screening_plan_v2_accepts_structured_amount_condition():
    plan = ScreeningPlanPayload.model_validate(
        {
            "target": "qmd_document",
            "plan_version": 2,
            "conditions": [
                {
                    "id": "amount_threshold",
                    "description": "合同总价大于等于100万元",
                    "condition_type": "amount",
                    "operator": "gte",
                    "value": 1000000,
                    "normalization_hint": {"currency": "CNY", "unit_aliases": ["万元", "人民币"]},
                    "qmd_queries": ["合同总价 人民币 金额"],
                    "verification_strategy": "grep_then_read",
                    "required_evidence_count": 1,
                    "negative_evidence_allowed": False,
                    "structured": True,
                }
            ],
            "decision_policy": "all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        }
    )

    condition = plan.conditions[0]
    assert plan.plan_version == 2
    assert condition.condition_type == "amount"
    assert condition.operator == "gte"
    assert condition.value == 1000000
    assert condition.verification_strategy == "grep_then_read"


def test_screening_plan_v1_still_accepts_existing_shape():
    plan = ScreeningPlanPayload(
        target="qmd_document",
        conditions=[
            ScreeningCondition(
                id="general_match",
                description="包含验收付款条款",
                operator="semantic_match",
                value="验收付款条款",
                qmd_queries=["验收付款"],
                evidence_required=1,
                structured=False,
            )
        ],
        decision_policy="phase1_keyword_candidate_uncertain_on_structured_comparison",
    )

    assert plan.plan_version == 1
    assert plan.conditions[0].condition_type == "semantic_risk"
    assert plan.conditions[0].required_evidence_count == 1


def test_phase3_enums_are_string_values():
    assert ConditionVerdictValue.satisfied.value == "satisfied"
    assert VerificationStatus.deep_read_verified.value == "deep_read_verified"
    assert EvidenceRole.supporting.value == "supporting"
```

- [ ] **Step 2: Run the schema test and verify it fails**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_plan_schema.py -v
```

Expected: FAIL because `ConditionVerdictValue`, Phase 3 fields, and v2 decision policy do not exist.

- [ ] **Step 3: Add Phase 3 enums**

Modify `backend/app/enums.py` by adding these enum classes below `ReviewStatus` and extending `AuditEventType`:

```python
class ConditionVerdictValue(StrEnum):
    satisfied = "satisfied"
    not_satisfied = "not_satisfied"
    unknown = "unknown"
    conflicting = "conflicting"


class ConditionType(StrEnum):
    amount = "amount"
    date = "date"
    party = "party"
    clause_presence = "clause_presence"
    clause_absence = "clause_absence"
    semantic_risk = "semantic_risk"
    keyword = "keyword"


class ConditionOperator(StrEnum):
    semantic_match = "semantic_match"
    gte = "gte"
    lte = "lte"
    eq = "eq"
    contains = "contains"
    not_contains = "not_contains"
    before = "before"
    after = "after"


class VerificationStrategy(StrEnum):
    query_only = "query_only"
    grep_then_read = "grep_then_read"
    doc_query = "doc_query"
    toc_guided_read = "toc_guided_read"


class VerificationStatus(StrEnum):
    query_only = "query_only"
    deep_read_verified = "deep_read_verified"
    partially_verified = "partially_verified"
    verification_failed = "verification_failed"


class UncertainReason(StrEnum):
    missing_evidence = "missing_evidence"
    conflicting_evidence = "conflicting_evidence"
    low_retrieval_confidence = "low_retrieval_confidence"
    ambiguous_requirement = "ambiguous_requirement"
    model_validation_failed = "model_validation_failed"
    verification_failed = "verification_failed"


class EvidenceRole(StrEnum):
    retrieval_candidate = "retrieval_candidate"
    supporting = "supporting"
    contradicting = "contradicting"
    missing_context = "missing_context"


class EvidenceSourceTool(StrEnum):
    query = "query"
    doc_grep = "doc_grep"
    doc_read = "doc_read"
    doc_query = "doc_query"
    doc_elements = "doc_elements"
```

Add these values to `AuditEventType`:

```python
    document_previewed = "document_previewed"
    document_opened = "document_opened"
    document_downloaded = "document_downloaded"
    agent_eval_run = "agent_eval_run"
```

- [ ] **Step 4: Extend Pydantic schemas**

Modify imports in `backend/app/schemas.py`:

```python
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
```

Replace `ScreeningCondition` and `ScreeningPlanPayload` with:

```python
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
```

Append these schemas after `ContractScreeningDecision`:

```python
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
```

Extend `DocumentResultItem` with nullable Phase 3 fields:

```python
    decision_basis: dict[str, Any] = Field(default_factory=dict)
    uncertain_reasons: list[UncertainReason] = Field(default_factory=list)
    evidence_support_rate: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.query_only
```

- [ ] **Step 5: Run schema tests and existing agent tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_plan_schema.py tests/test_langgraph_agent.py -v
```

Expected: PASS. Existing plan construction continues to work with defaults.

- [ ] **Step 6: Commit**

```bash
git add backend/app/enums.py backend/app/schemas.py backend/tests/test_phase3_plan_schema.py
git commit -m "feat(agent): add phase 3 evidence schemas"
```

---

### Task 2: Database Migration For Verdicts And Result Metadata

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0004_phase3_trustworthy_evidence.py`
- Test: `backend/tests/test_phase3_models_migration.py`

- [ ] **Step 1: Write failing model and migration tests**

Create `backend/tests/test_phase3_models_migration.py`:

```python
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect

from app.enums import ConditionVerdictValue, ResultDecision, VerificationStatus
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask


def test_phase3_columns_exist_in_test_schema(db_session):
    session, _ = db_session
    inspector = inspect(session.get_bind())
    result_columns = {column["name"] for column in inspector.get_columns("screening_document_results")}
    assert {"decision_basis", "uncertain_reasons", "evidence_support_rate", "verification_status"} <= result_columns
    assert "condition_verdicts" in inspector.get_table_names()


def test_condition_verdict_persists_evidence_payloads(db_session):
    session, _ = db_session
    task = ScreeningTask(id=uuid4(), owner_id="internal-user", title="金额筛选", raw_query="金额大于100万", metrics={})
    session.add(task)
    session.flush()
    result = ScreeningDocumentResult(
        task_id=task.id,
        document_uri="qmd://company_docs/contracts/a.md",
        document_path="contracts/a.md",
        document_title="A合同",
        collection="company_docs",
        decision=ResultDecision.uncertain.value,
        reason="missing_evidence",
        matched_conditions=[],
        missing_conditions=["amount"],
        evidence=[],
        confidence=0.3,
        uncertain_reasons=["missing_evidence"],
        verification_status=VerificationStatus.verification_failed.value,
    )
    session.add(result)
    verdict = ConditionVerdict(
        task_id=task.id,
        document_uri="qmd://company_docs/contracts/a.md",
        condition_id="amount",
        verdict=ConditionVerdictValue.unknown.value,
        confidence=0.2,
        supporting_evidence=[],
        contradicting_evidence=[],
        missing_reason="未找到金额证据",
        verification_method="grep_then_read",
    )
    session.add(verdict)
    session.commit()

    stored = session.get(ConditionVerdict, verdict.id)
    assert stored.missing_reason == "未找到金额证据"
    assert stored.supporting_evidence == []


def test_phase3_migration_file_contains_expected_tables_and_columns():
    migration = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0004_phase3_trustworthy_evidence.py").read_text(encoding="utf-8")
    assert "condition_verdicts" in migration
    assert "agent_eval_cases" in migration
    assert "agent_eval_runs" in migration
    assert "decision_basis" in migration
    assert "verification_status" in migration
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_models_migration.py -v
```

Expected: FAIL because model and migration do not exist.

- [ ] **Step 3: Extend models**

Modify the imports in `backend/app/models.py`:

```python
from app.enums import ParseStatus, TaskStatus, VerificationStatus
```

Add these fields to `ScreeningDocumentResult` after `confidence`:

```python
    decision_basis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    uncertain_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_support_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default=VerificationStatus.query_only.value)
```

Add these model classes before `ContractScreeningResult`:

```python
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
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/0004_phase3_trustworthy_evidence.py`:

```python
"""phase3 trustworthy evidence

Revision ID: 0004_phase3_trustworthy_evidence
Revises: 0003_phase2_workbench
Create Date: 2026-06-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from app.db import uuid_type


revision = "0004_phase3_trustworthy_evidence"
down_revision = "0003_phase2_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("screening_document_results", sa.Column("decision_basis", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("screening_document_results", sa.Column("uncertain_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("screening_document_results", sa.Column("evidence_support_rate", sa.Float(), nullable=False, server_default="0"))
    op.add_column("screening_document_results", sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="query_only"))

    op.create_table(
        "condition_verdicts",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_uri", sa.Text(), nullable=False),
        sa.Column("condition_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("missing_reason", sa.Text(), nullable=True),
        sa.Column("verification_method", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "document_uri", "condition_id", name="uq_condition_verdict_task_doc_condition"),
    )
    op.create_index("ix_condition_verdicts_task_document", "condition_verdicts", ["task_id", "document_uri"])

    op.create_table(
        "agent_eval_cases",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_eval_runs",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("case_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("failures", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_eval_runs")
    op.drop_table("agent_eval_cases")
    op.drop_index("ix_condition_verdicts_task_document", table_name="condition_verdicts")
    op.drop_table("condition_verdicts")
    op.drop_column("screening_document_results", "verification_status")
    op.drop_column("screening_document_results", "evidence_support_rate")
    op.drop_column("screening_document_results", "uncertain_reasons")
    op.drop_column("screening_document_results", "decision_basis")
```

- [ ] **Step 5: Include Phase 3 fields in result serialization**

Modify `document_result_item()` in `backend/app/api/screening_tasks.py` by adding:

```python
        decision_basis=result.decision_basis,
        uncertain_reasons=result.uncertain_reasons,
        evidence_support_rate=result.evidence_support_rate,
        verification_status=result.verification_status,
```

- [ ] **Step 6: Run migration/model tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_models_migration.py tests/test_alembic_migrations.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/api/screening_tasks.py backend/alembic/versions/0004_phase3_trustworthy_evidence.py backend/tests/test_phase3_models_migration.py
git commit -m "feat(agent): persist condition verdicts"
```

---

### Task 3: MinerU Deep-Read Qmd Client

**Files:**
- Modify: `backend/app/services/retrieval/qmd_client.py`
- Test: `backend/tests/test_qmd_deep_read_client.py`

- [ ] **Step 1: Write failing qmd deep-read tests**

Create `backend/tests/test_qmd_deep_read_client.py`:

```python
import pytest

from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, normalize_qmd_file


def test_normalize_qmd_file_rejects_path_escape():
    with pytest.raises(QmdUnavailable):
        normalize_qmd_file("qmd://company_docs/../secrets.pdf", "company_docs")


def test_doc_read_calls_mcp_tool(monkeypatch):
    client = QmdClient(url="http://qmd.example/mcp")
    calls = []

    def fake_call_tool(name, arguments):
        calls.append((name, arguments))
        return {"structuredContent": {"text": "合同总价为人民币120万元", "page": 3, "anchor": "p3"}}

    monkeypatch.setattr(client, "_call_tool", fake_call_tool)

    payload = client.doc_read("qmd://company_docs/contracts/a.md", page=3, anchor=None, window=2)

    assert calls == [
        (
            "doc_read",
            {"document_uri": "qmd://company_docs/contracts/a.md", "page": 3, "anchor": None, "window": 2},
        )
    ]
    assert payload["text"] == "合同总价为人民币120万元"


def test_document_preview_falls_back_to_text_content(monkeypatch):
    client = QmdClient(url="http://qmd.example/mcp")

    def fake_call_tool(name, arguments):
        assert name == "doc_toc"
        return {"content": [{"type": "text", "text": "第一章 合同标的\n第二章 价款"}]}

    monkeypatch.setattr(client, "_call_tool", fake_call_tool)

    preview = client.document_preview("qmd://company_docs/contracts/a.md")

    assert preview["document_uri"] == "qmd://company_docs/contracts/a.md"
    assert preview["summary"] == "第一章 合同标的\n第二章 价款"
    assert preview["can_download"] is False
```

- [ ] **Step 2: Run qmd deep-read tests and verify they fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_qmd_deep_read_client.py -v
```

Expected: FAIL because methods do not exist and URI escaping is not rejected.

- [ ] **Step 3: Add safe URI validation and MCP helper methods**

Modify `backend/app/services/retrieval/qmd_client.py`:

```python
def validate_qmd_document_uri(document_uri: str) -> str:
    value = document_uri.strip()
    if not value.startswith("qmd://"):
        raise QmdUnavailable("qmd document URI must start with qmd://")
    if "\x00" in value or ".." in value.split("qmd://", 1)[1].split("/"):
        raise QmdUnavailable("qmd document URI contains an unsafe path segment")
    return value
```

Add methods to `QmdClient` after `query()`:

```python
    def list_tools(self) -> list[str]:
        if self._session_id is None:
            self._initialize()
        response = self._post({"jsonrpc": "2.0", "id": self._allocate_id(), "method": "tools/list", "params": {}})
        tools = response.get("result", {}).get("tools", [])
        return [str(item.get("name")) for item in tools if isinstance(item, dict) and item.get("name")]

    def doc_toc(self, document_uri: str) -> dict[str, Any]:
        return self._deep_read_tool("doc_toc", {"document_uri": validate_qmd_document_uri(document_uri)})

    def doc_grep(self, document_uri: str, pattern: str) -> dict[str, Any]:
        return self._deep_read_tool("doc_grep", {"document_uri": validate_qmd_document_uri(document_uri), "pattern": pattern})

    def doc_read(self, document_uri: str, page: int | None = None, anchor: str | None = None, window: int = 2) -> dict[str, Any]:
        return self._deep_read_tool(
            "doc_read",
            {"document_uri": validate_qmd_document_uri(document_uri), "page": page, "anchor": anchor, "window": window},
        )

    def doc_query(self, document_uri: str, question: str) -> dict[str, Any]:
        return self._deep_read_tool("doc_query", {"document_uri": validate_qmd_document_uri(document_uri), "question": question})

    def doc_elements(self, document_uri: str, page: int | None = None, anchor: str | None = None) -> dict[str, Any]:
        return self._deep_read_tool("doc_elements", {"document_uri": validate_qmd_document_uri(document_uri), "page": page, "anchor": anchor})

    def document_preview(self, document_uri: str) -> dict[str, Any]:
        safe_uri = validate_qmd_document_uri(document_uri)
        payload = self.doc_toc(safe_uri)
        structured = payload.get("structuredContent")
        if isinstance(structured, dict):
            return {
                "document_uri": safe_uri,
                "document_title": structured.get("title"),
                "collection": structured.get("collection"),
                "toc": structured.get("toc", []) if isinstance(structured.get("toc"), list) else [],
                "summary": structured.get("summary"),
                "can_open": bool(structured.get("open_url")),
                "can_download": bool(structured.get("download_url")),
                "open_url": structured.get("open_url"),
                "download_url": structured.get("download_url"),
            }
        text = extract_text(payload)
        return {"document_uri": safe_uri, "toc": [], "summary": text or None, "can_open": False, "can_download": False}

    def _deep_read_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call_tool(name, arguments)
```

Modify `normalize_qmd_file()` to call `validate_qmd_document_uri()` before returning:

```python
    document_uri = validate_qmd_document_uri(f"qmd://{collection}/{path}")
    return collection, path, document_uri
```

- [ ] **Step 4: Run qmd client tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_qmd_client.py tests/test_qmd_deep_read_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retrieval/qmd_client.py backend/tests/test_qmd_deep_read_client.py
git commit -m "feat(qmd): add deep read client methods"
```

---

### Task 4: Condition Verification Service And Agent Integration

**Files:**
- Modify: `backend/app/services/agent/llm.py`
- Create: `backend/app/services/agent/verifier.py`
- Modify: `backend/app/services/agent/langgraph_agent.py`
- Test: `backend/tests/test_phase3_agent_verification.py`

- [ ] **Step 1: Write failing verification tests**

Create `backend/tests/test_phase3_agent_verification.py`:

```python
from uuid import uuid4

from sqlalchemy import select

from app.enums import ConditionVerdictValue, ResultDecision, TaskStatus, VerificationStatus
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask
from app.schemas import ScreeningCondition, ScreeningPlanPayload


class DeepReadQmd:
    def status(self):
        return {"collections": [{"name": "company_docs"}]}

    def query(self, query_text: str, collections: list[str], limit: int):
        return [
            {
                "docid": "doc-1",
                "file": "qmd://company_docs/contracts/a.md",
                "title": "A合同",
                "score": 0.91,
                "snippet": "合同总价为人民币120万元。",
                "page_number": 3,
            }
        ]

    def doc_grep(self, document_uri: str, pattern: str):
        return {"structuredContent": {"matches": [{"page": 3, "text": "合同总价为人民币120万元。", "anchor": "p3"}]}}

    def doc_read(self, document_uri: str, page=None, anchor=None, window=2):
        return {"structuredContent": {"text": "第三页：合同总价为人民币120万元，含税。", "page": page, "anchor": anchor}}


class VerdictLlm:
    def plan(self, raw_query: str):
        return ScreeningPlanPayload(
            target="qmd_document",
            plan_version=2,
            conditions=[
                ScreeningCondition(
                    id="amount",
                    description="合同总价大于等于100万元",
                    condition_type="amount",
                    operator="gte",
                    value=1000000,
                    qmd_queries=["合同总价 人民币 金额"],
                    verification_strategy="grep_then_read",
                    required_evidence_count=1,
                    evidence_required=1,
                    structured=True,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )

    def refine_queries(self, raw_query, plan, missing_condition_ids):
        return {}

    def classify_document(self, plan, document):
        raise AssertionError("Phase 3 should use condition verdicts before document result")

    def judge_condition(self, plan, condition, document, evidence):
        return {
            "verdict": "satisfied",
            "confidence": 0.86,
            "supporting_evidence": evidence,
            "contradicting_evidence": [],
            "missing_reason": None,
        }


def test_agent_persists_condition_verdicts_and_verified_document_result(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="金额筛选",
        raw_query="筛选合同总价大于等于100万元的合同",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    session.add(task)
    session.commit()

    ContractScreeningAgent(llm=VerdictLlm(), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.satisfied.value
    assert verdict.supporting_evidence[0]["source_tool"] == "doc_read"

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.included.value
    assert result.verification_status == VerificationStatus.deep_read_verified.value
    assert result.evidence_support_rate == 1.0
```

- [ ] **Step 2: Run the verification test and verify it fails**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_agent_verification.py -v
```

Expected: FAIL because verifier and `judge_condition` do not exist.

- [ ] **Step 3: Add LLM protocol and condition judge**

Modify `AgentLlm` in `backend/app/services/agent/llm.py`:

```python
    def judge_condition(self, plan: ScreeningPlanPayload, condition: Any, document: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError
```

Add method to `OpenAICompatibleAgentLlm`:

```python
    def judge_condition(self, plan: ScreeningPlanPayload, condition: Any, document: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        return self._json(
            "你是合同筛选条件核验器。只能基于给定证据判断。证据不足输出unknown，证据冲突输出conflicting。只输出JSON。",
            {
                "task": "判断单份文档是否满足单个筛选条件。",
                "plan": plan.model_dump(),
                "condition": condition.model_dump() if hasattr(condition, "model_dump") else condition,
                "document": document,
                "evidence": evidence,
                "schema": {
                    "verdict": "satisfied|not_satisfied|unknown|conflicting",
                    "confidence": 0.0,
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "missing_reason": "证据不足时填写",
                },
            },
        )
```

- [ ] **Step 4: Create verifier service**

Create `backend/app/services/agent/verifier.py`:

```python
from typing import Any

from sqlalchemy.orm import Session

from app.enums import ConditionVerdictValue, EvidenceRole, EvidenceSourceTool, ResultDecision, UncertainReason, VerificationStatus
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask
from app.schemas import ScreeningPlanPayload
from app.services.agent.aggregator import aggregate_document_candidates


def verify_documents(session: Session, task: ScreeningTask, plan: ScreeningPlanPayload, qmd: Any, llm: Any) -> int:
    documents = aggregate_document_candidates(session, task.id, plan)
    for document in documents.values():
        verdicts = []
        for condition in plan.conditions:
            evidence = _deep_read_evidence(qmd, document, condition)
            raw = llm.judge_condition(plan, condition, _serializable_document(document), evidence)
            verdict = _persist_verdict(session, task, document, condition.id, condition.verification_strategy.value, raw)
            verdicts.append(verdict)
        _persist_document_result(session, task, document, plan, verdicts)
    return len(documents)


def _deep_read_evidence(qmd: Any, document: dict[str, Any], condition: Any) -> list[dict[str, Any]]:
    document_uri = str(document["document_uri"])
    query_text = " ".join(condition.qmd_queries)
    evidence = []
    try:
        if condition.verification_strategy.value == "grep_then_read":
            grep_payload = qmd.doc_grep(document_uri, query_text)
            matches = _structured(grep_payload).get("matches", [])
            first = matches[0] if matches else {}
            read_payload = qmd.doc_read(document_uri, page=first.get("page"), anchor=first.get("anchor"), window=2)
            text = _structured(read_payload).get("text") or first.get("text") or ""
            if text:
                evidence.append(
                    {
                        "page": first.get("page"),
                        "text": text,
                        "source": "qmd",
                        "score": None,
                        "condition_id": condition.id,
                        "artifact_ref": document_uri,
                        "role": EvidenceRole.supporting.value,
                        "source_tool": EvidenceSourceTool.doc_read.value,
                        "document_uri": document_uri,
                        "document_path": document.get("document_path"),
                        "collection": document.get("collection"),
                        "anchor": first.get("anchor"),
                        "context": text,
                        "used_for_decision": True,
                    }
                )
    except Exception:
        return []
    return evidence


def _persist_verdict(session: Session, task: ScreeningTask, document: dict[str, Any], condition_id: str, method: str, raw: dict[str, Any]) -> ConditionVerdict:
    verdict_value = str(raw.get("verdict") or ConditionVerdictValue.unknown.value)
    if verdict_value not in {item.value for item in ConditionVerdictValue}:
        verdict_value = ConditionVerdictValue.unknown.value
    row = ConditionVerdict(
        task_id=task.id,
        document_uri=str(document["document_uri"]),
        condition_id=condition_id,
        verdict=verdict_value,
        confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
        supporting_evidence=list(raw.get("supporting_evidence") or []),
        contradicting_evidence=list(raw.get("contradicting_evidence") or []),
        missing_reason=raw.get("missing_reason"),
        verification_method=method,
    )
    session.add(row)
    return row


def _persist_document_result(session: Session, task: ScreeningTask, document: dict[str, Any], plan: ScreeningPlanPayload, verdicts: list[ConditionVerdict]) -> None:
    all_satisfied = all(verdict.verdict == ConditionVerdictValue.satisfied.value for verdict in verdicts)
    any_conflict = any(verdict.verdict == ConditionVerdictValue.conflicting.value for verdict in verdicts)
    any_unknown = any(verdict.verdict == ConditionVerdictValue.unknown.value for verdict in verdicts)
    if all_satisfied:
        decision = ResultDecision.included.value
        uncertain_reasons = []
    elif any_conflict or any_unknown:
        decision = ResultDecision.uncertain.value
        uncertain_reasons = [UncertainReason.conflicting_evidence.value] if any_conflict else [UncertainReason.missing_evidence.value]
    else:
        decision = ResultDecision.excluded.value
        uncertain_reasons = []
    supporting = [item for verdict in verdicts for item in verdict.supporting_evidence]
    support_rate = _support_rate(verdicts)
    session.add(
        ScreeningDocumentResult(
            task_id=task.id,
            document_uri=str(document["document_uri"]),
            document_path=str(document["document_path"]),
            document_title=document.get("document_title"),
            collection=str(document["collection"]),
            decision=decision,
            reason="condition_verdicts",
            matched_conditions=[v.condition_id for v in verdicts if v.verdict == ConditionVerdictValue.satisfied.value],
            missing_conditions=[v.condition_id for v in verdicts if v.verdict in {ConditionVerdictValue.unknown.value, ConditionVerdictValue.not_satisfied.value}],
            evidence=supporting[:10],
            confidence=min([v.confidence for v in verdicts] or [0.0]),
            decision_basis={v.condition_id: v.verdict for v in verdicts},
            uncertain_reasons=uncertain_reasons,
            evidence_support_rate=support_rate,
            verification_status=VerificationStatus.deep_read_verified.value if support_rate == 1.0 else VerificationStatus.partially_verified.value,
        )
    )


def _support_rate(verdicts: list[ConditionVerdict]) -> float:
    if not verdicts:
        return 0.0
    supported = sum(1 for verdict in verdicts if verdict.supporting_evidence)
    return round(supported / len(verdicts), 4)


def _structured(payload: dict[str, Any]) -> dict[str, Any]:
    structured = payload.get("structuredContent")
    return structured if isinstance(structured, dict) else {}


def _serializable_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_uri": document["document_uri"],
        "document_path": document["document_path"],
        "document_title": document.get("document_title"),
        "collection": document.get("collection"),
    }
```

- [ ] **Step 5: Wire verifier into LangGraph**

Modify `backend/app/services/agent/langgraph_agent.py`:

Add import:

```python
from app.services.agent.verifier import verify_documents
```

Change graph construction:

```python
        graph.add_node("verify", self._verify)
        graph.add_conditional_edges("retrieve", self._route_after_retrieve, {True: "refine_queries", False: "verify"})
        graph.add_edge("verify", END)
```

Add method:

```python
    def _verify(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        plan = state["plan"]
        task.status = TaskStatus.classifying.value
        task.current_stage = TaskStatus.classifying.value
        task.progress_percent = 75
        publish_stream_event(session, task, "verification_started", {}, status=TaskStatus.classifying.value, current_stage=TaskStatus.classifying.value, progress_percent=75)
        document_count = verify_documents(session, task, plan, self.qmd, self.llm)
        task.progress_percent = 95
        publish_stream_event(session, task, "verification_completed", {"document_count": document_count}, status=TaskStatus.classifying.value, current_stage=TaskStatus.classifying.value, progress_percent=95)
        return {**state, "document_count": document_count}
```

Keep `_classify()` in the file for compatibility until no tests call it directly.

- [ ] **Step 6: Run agent verification tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_agent_verification.py tests/test_langgraph_agent.py -v
```

Expected: PASS after updating `ScriptedAgentLlm` in `test_langgraph_agent.py` with a `judge_condition()` method or routing Phase 1 plans to `_classify()`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agent/llm.py backend/app/services/agent/verifier.py backend/app/services/agent/langgraph_agent.py backend/tests/test_phase3_agent_verification.py backend/tests/test_langgraph_agent.py
git commit -m "feat(agent): verify documents by condition"
```

---

### Task 5: Evidence Ledger And Qmd Document APIs

**Files:**
- Create: `backend/app/services/agent/evidence_ledger.py`
- Modify: `backend/app/api/screening_tasks.py`
- Create: `backend/app/api/qmd_documents.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_phase3_evidence_api.py`
- Test: `backend/tests/test_qmd_documents_api.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/test_phase3_evidence_api.py`:

```python
from uuid import uuid4

from app.enums import ConditionVerdictValue, ResultDecision
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask


def test_condition_verdicts_endpoint_returns_task_matrix(client, db_session):
    session, _ = db_session
    task = ScreeningTask(id=uuid4(), owner_id="internal-user", title="金额筛选", raw_query="金额大于100万", metrics={})
    session.add(task)
    session.flush()
    session.add(
        ConditionVerdict(
            task_id=task.id,
            document_uri="qmd://company_docs/contracts/a.md",
            condition_id="amount",
            verdict=ConditionVerdictValue.satisfied.value,
            confidence=0.9,
            supporting_evidence=[],
            contradicting_evidence=[],
            verification_method="grep_then_read",
        )
    )
    session.commit()

    response = client.get(f"/api/screening-tasks/{task.id}/condition-verdicts")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["condition_id"] == "amount"
    assert body["items"][0]["verdict"] == "satisfied"


def test_evidence_ledger_endpoint_flattens_document_and_verdict_evidence(client, db_session):
    session, _ = db_session
    task = ScreeningTask(id=uuid4(), owner_id="internal-user", title="金额筛选", raw_query="金额大于100万", metrics={})
    session.add(task)
    session.flush()
    session.add(
        ScreeningDocumentResult(
            task_id=task.id,
            document_uri="qmd://company_docs/contracts/a.md",
            document_path="contracts/a.md",
            document_title="A合同",
            collection="company_docs",
            decision=ResultDecision.included.value,
            reason="condition_verdicts",
            matched_conditions=["amount"],
            missing_conditions=[],
            evidence=[
                {
                    "page": 3,
                    "text": "合同总价为人民币120万元",
                    "source": "qmd",
                    "score": None,
                    "condition_id": "amount",
                    "artifact_ref": "qmd://company_docs/contracts/a.md",
                    "role": "supporting",
                    "source_tool": "doc_read",
                    "document_uri": "qmd://company_docs/contracts/a.md",
                    "used_for_decision": True,
                }
            ],
            confidence=0.9,
        )
    )
    session.commit()

    response = client.get(f"/api/screening-tasks/{task.id}/evidence-ledger")

    assert response.status_code == 200
    assert response.json()["items"][0]["role"] == "supporting"
```

Create `backend/tests/test_qmd_documents_api.py`:

```python
def test_qmd_document_preview_returns_preview_payload(client, monkeypatch):
    import app.api.qmd_documents as routes

    class FakeQmd:
        def document_preview(self, document_uri):
            return {
                "document_uri": document_uri,
                "document_title": "A合同",
                "collection": "company_docs",
                "toc": [{"title": "价款", "page": 3}],
                "summary": "价款章节",
                "can_open": False,
                "can_download": False,
            }

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get("/api/qmd-documents/preview?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md")

    assert response.status_code == 200
    assert response.json()["document_title"] == "A合同"


def test_qmd_document_download_unavailable_returns_clear_error(client, monkeypatch):
    import app.api.qmd_documents as routes

    class FakeQmd:
        def document_preview(self, document_uri):
            return {"document_uri": document_uri, "can_download": False}

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get("/api/qmd-documents/download?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "qmd_download_unavailable"
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_evidence_api.py tests/test_qmd_documents_api.py -v
```

Expected: FAIL because APIs do not exist.

- [ ] **Step 3: Create evidence ledger service**

Create `backend/app/services/agent/evidence_ledger.py`:

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EvidenceRole, EvidenceSourceTool
from app.models import ScreeningDocumentResult


def build_evidence_ledger(session: Session, task_id: UUID) -> list[dict]:
    results = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task_id)).all()
    items = []
    for result in results:
        for evidence in result.evidence:
            item = dict(evidence)
            item.setdefault("role", EvidenceRole.retrieval_candidate.value)
            item.setdefault("source_tool", EvidenceSourceTool.query.value)
            item.setdefault("document_uri", result.document_uri)
            item.setdefault("document_path", result.document_path)
            item.setdefault("collection", result.collection)
            item.setdefault("used_for_decision", item.get("role") == EvidenceRole.supporting.value)
            items.append(item)
    return items
```

- [ ] **Step 4: Add screening task endpoints**

Modify imports in `backend/app/api/screening_tasks.py`:

```python
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask, StreamEvent
from app.schemas import ConditionVerdictItem, ConditionVerdictResponse, EvidenceLedgerResponse, LedgerEvidenceItem
from app.services.agent.evidence_ledger import build_evidence_ledger
```

Add endpoints after `get_results()`:

```python
@router.get("/{task_id}/condition-verdicts", response_model=ConditionVerdictResponse)
def get_condition_verdicts(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    rows = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id).order_by(ConditionVerdict.document_uri, ConditionVerdict.condition_id)).all()
    return ConditionVerdictResponse(
        task_id=task.id,
        items=[
            ConditionVerdictItem(
                verdict_id=row.id,
                task_id=row.task_id,
                document_uri=row.document_uri,
                condition_id=row.condition_id,
                verdict=row.verdict,
                confidence=row.confidence,
                supporting_evidence=[LedgerEvidenceItem(**item) for item in row.supporting_evidence],
                contradicting_evidence=[LedgerEvidenceItem(**item) for item in row.contradicting_evidence],
                missing_reason=row.missing_reason,
                verification_method=row.verification_method,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/{task_id}/evidence-ledger", response_model=EvidenceLedgerResponse)
def get_evidence_ledger(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    return EvidenceLedgerResponse(task_id=task.id, items=[LedgerEvidenceItem(**item) for item in build_evidence_ledger(session, task.id)])
```

- [ ] **Step 5: Create qmd document router**

Create `backend/app/api/qmd_documents.py`:

```python
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.api.auth import AuthContext, get_auth
from app.enums import AuditEventType
from app.errors import ApiError
from app.schemas import QmdDocumentPreviewResponse, QmdEvidenceContextResponse
from app.services.audit import write_audit
from app.db import get_session
from app.services.retrieval.qmd_client import QmdClient
from sqlalchemy.orm import Session


router = APIRouter()


@router.get("/preview", response_model=QmdDocumentPreviewResponse)
def preview_document(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    payload = QmdClient().document_preview(document_uri)
    write_audit(session, AuditEventType.document_previewed.value, {"document_uri": document_uri}, actor_id=auth.owner_id)
    session.commit()
    return QmdDocumentPreviewResponse(**payload)


@router.get("/evidence-context", response_model=QmdEvidenceContextResponse)
def evidence_context(document_uri: str, condition_id: str | None = None, page: int | None = None, auth: AuthContext = Depends(get_auth)):
    payload = QmdClient().doc_read(document_uri, page=page, anchor=None, window=2)
    structured = payload.get("structuredContent") if isinstance(payload.get("structuredContent"), dict) else {}
    text = structured.get("text") or ""
    if not text:
        raise ApiError("qmd_preview_unavailable", "Unable to load qmd document context", 404)
    return QmdEvidenceContextResponse(document_uri=document_uri, condition_id=condition_id, page=page, text=text, source_tool="doc_read")


@router.get("/open-link")
def open_link(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    preview = QmdClient().document_preview(document_uri)
    url = preview.get("open_url")
    if not url:
        raise ApiError("qmd_preview_unavailable", "qmd document open link is unavailable", 404)
    write_audit(session, AuditEventType.document_opened.value, {"document_uri": document_uri}, actor_id=auth.owner_id)
    session.commit()
    return RedirectResponse(str(url), status_code=302)


@router.get("/download")
def download(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    preview = QmdClient().document_preview(document_uri)
    url = preview.get("download_url")
    if not url:
        raise ApiError("qmd_download_unavailable", "qmd document download is unavailable", 404)
    write_audit(session, AuditEventType.document_downloaded.value, {"document_uri": document_uri}, actor_id=auth.owner_id)
    session.commit()
    return RedirectResponse(str(url), status_code=302)
```

Modify `backend/app/main.py` router imports and includes:

```python
from app.api import contracts, health, qmd_documents, screening_tasks

app.include_router(qmd_documents.router, prefix="/api/qmd-documents", tags=["qmd-documents"])
```

- [ ] **Step 6: Run API tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase3_evidence_api.py tests/test_qmd_documents_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/agent/evidence_ledger.py backend/app/api/screening_tasks.py backend/app/api/qmd_documents.py backend/app/main.py backend/tests/test_phase3_evidence_api.py backend/tests/test_qmd_documents_api.py
git commit -m "feat(api): expose evidence ledger and qmd preview"
```

---

### Task 6: Agent Evaluation Metrics

**Files:**
- Create: `backend/app/services/evals.py`
- Create: `backend/app/api/agent_evals.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_agent_evals.py`

- [ ] **Step 1: Write failing eval tests**

Create `backend/tests/test_agent_evals.py`:

```python
from app.services.evals import compute_eval_metrics


def test_compute_eval_metrics_counts_precision_recall_and_support():
    cases = [
        {
            "expected": {"included": ["qmd://docs/a.md"], "excluded": ["qmd://docs/b.md"], "uncertain": ["qmd://docs/c.md"]},
            "actual": [
                {"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"},
                {"document_uri": "qmd://docs/b.md", "decision": "included", "evidence_support_rate": 0.0, "verification_status": "query_only"},
                {"document_uri": "qmd://docs/c.md", "decision": "uncertain", "evidence_support_rate": 0.0, "verification_status": "verification_failed"},
            ],
        }
    ]

    metrics = compute_eval_metrics(cases, schema_failures=1, verification_failures=1)

    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1.0
    assert metrics["uncertain_rate"] == 1 / 3
    assert metrics["evidence_support_rate"] == 0.5
    assert metrics["schema_failure_rate"] == 1.0
    assert metrics["verification_failure_rate"] == 1.0


def test_agent_eval_run_endpoint_persists_metrics(client, db_session):
    response = client.post(
        "/api/agent-evals/run",
        json={
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                    "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["precision"] == 1.0
    assert body["metrics"]["recall"] == 1.0
```

- [ ] **Step 2: Run eval tests and verify they fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_agent_evals.py -v
```

Expected: FAIL because service and router do not exist.

- [ ] **Step 3: Implement eval metric service**

Create `backend/app/services/evals.py`:

```python
def compute_eval_metrics(cases: list[dict], schema_failures: int = 0, verification_failures: int = 0) -> dict[str, float]:
    true_positive = 0
    predicted_included = 0
    expected_included = 0
    uncertain_count = 0
    total_predictions = 0
    included_support_sum = 0.0

    for case in cases:
        expected = case.get("expected", {})
        expected_included_set = set(expected.get("included", []))
        expected_included += len(expected_included_set)
        for item in case.get("actual", []):
            total_predictions += 1
            decision = item.get("decision")
            uri = item.get("document_uri")
            if decision == "uncertain":
                uncertain_count += 1
            if decision == "included":
                predicted_included += 1
                included_support_sum += float(item.get("evidence_support_rate") or 0.0)
                if uri in expected_included_set:
                    true_positive += 1

    return {
        "precision": _safe_div(true_positive, predicted_included),
        "recall": _safe_div(true_positive, expected_included),
        "uncertain_rate": _safe_div(uncertain_count, total_predictions),
        "evidence_support_rate": _safe_div(included_support_sum, predicted_included),
        "schema_failure_rate": _safe_div(schema_failures, max(1, len(cases))),
        "verification_failure_rate": _safe_div(verification_failures, max(1, len(cases))),
    }


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
```

- [ ] **Step 4: Implement eval router**

Create `backend/app/api/agent_evals.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.db import get_session
from app.enums import AuditEventType
from app.models import AgentEvalRun
from app.services.audit import write_audit
from app.services.evals import compute_eval_metrics


router = APIRouter()


class EvalRunRequest(BaseModel):
    cases: list[dict] = Field(min_length=1)
    schema_failures: int = 0
    verification_failures: int = 0


@router.post("/run")
def run_eval(payload: EvalRunRequest, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    metrics = compute_eval_metrics(payload.cases, payload.schema_failures, payload.verification_failures)
    run = AgentEvalRun(case_ids=[], metrics=metrics, failures=[])
    session.add(run)
    session.flush()
    write_audit(session, AuditEventType.agent_eval_run.value, {"run_id": str(run.id), "metrics": metrics}, actor_id=auth.owner_id)
    session.commit()
    return {"run_id": str(run.id), "metrics": metrics, "failures": []}


@router.get("/{run_id}")
def get_eval_run(run_id: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    run = session.get(AgentEvalRun, run_id)
    if run is None:
        from app.errors import ApiError

        raise ApiError("not_found", "Not found", 404)
    return {"run_id": str(run.id), "metrics": run.metrics, "failures": run.failures, "created_at": run.created_at}
```

Modify `backend/app/main.py`:

```python
from app.api import agent_evals, contracts, health, qmd_documents, screening_tasks

app.include_router(agent_evals.router, prefix="/api/agent-evals", tags=["agent-evals"])
```

- [ ] **Step 5: Run eval tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_agent_evals.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/evals.py backend/app/api/agent_evals.py backend/app/main.py backend/tests/test_agent_evals.py
git commit -m "feat(agent): add evaluation metrics"
```

---

### Task 7: Frontend Condition Matrix, Ledger, And Preview

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/TaskProgressPage.tsx`
- Modify: `frontend/src/lib/errorMessages.ts`
- Modify: `frontend/src/styles/contract-agent.css`
- Create: `frontend/tests/phase3Api.test.ts`
- Modify: `frontend/tests/TaskProgressPage.test.tsx`

- [ ] **Step 1: Write failing frontend API tests**

Create `frontend/tests/phase3Api.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getConditionVerdicts, getEvidenceLedger, getQmdEvidenceContext, getQmdPreview } from '../src/lib/api';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('phase 3 api client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('loads condition verdicts and evidence ledger', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }))
      .mockResolvedValueOnce(jsonResponse({ task_id: 'task-1', items: [] }));
    vi.stubGlobal('fetch', fetchMock);

    await getConditionVerdicts('task-1');
    await getEvidenceLedger('task-1');

    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/condition-verdicts');
    expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/evidence-ledger');
  });

  it('encodes qmd document uri for preview and context', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/a.md', toc: [], can_open: false, can_download: false }))
      .mockResolvedValueOnce(jsonResponse({ document_uri: 'qmd://company_docs/a.md', text: '上下文', source_tool: 'doc_read' }));
    vi.stubGlobal('fetch', fetchMock);

    await getQmdPreview('qmd://company_docs/a.md');
    await getQmdEvidenceContext({ document_uri: 'qmd://company_docs/a.md', condition_id: 'amount', page: 3 });

    expect(String(fetchMock.mock.calls[0][0])).toContain('document_uri=qmd%3A%2F%2Fcompany_docs%2Fa.md');
    expect(String(fetchMock.mock.calls[1][0])).toContain('condition_id=amount');
  });
});
```

Add this assertion to `frontend/tests/TaskProgressPage.test.tsx` in the final-results test after the document appears:

```typescript
expect(await screen.findByText('条件矩阵')).toBeInTheDocument();
expect(screen.getByText('证据账本')).toBeInTheDocument();
```

- [ ] **Step 2: Run frontend tests and verify they fail**

Run:

```bash
cd frontend
npm test -- --run phase3Api TaskProgressPage
```

Expected: FAIL because API client functions and UI sections do not exist.

- [ ] **Step 3: Add frontend types**

Append to `frontend/src/lib/types.ts`:

```typescript
export type ConditionVerdictValue = 'satisfied' | 'not_satisfied' | 'unknown' | 'conflicting';
export type VerificationStatus = 'query_only' | 'deep_read_verified' | 'partially_verified' | 'verification_failed';
export type EvidenceRole = 'retrieval_candidate' | 'supporting' | 'contradicting' | 'missing_context';
export type EvidenceSourceTool = 'query' | 'doc_grep' | 'doc_read' | 'doc_query' | 'doc_elements';

export interface LedgerEvidenceItem extends EvidenceItem {
  role: EvidenceRole;
  source_tool: EvidenceSourceTool;
  document_uri: string | null;
  document_path: string | null;
  collection: string | null;
  anchor: string | null;
  context: string | null;
  used_for_decision: boolean;
}

export interface ConditionVerdictItem {
  verdict_id: string;
  task_id: string;
  document_uri: string;
  condition_id: string;
  verdict: ConditionVerdictValue;
  confidence: number;
  supporting_evidence: LedgerEvidenceItem[];
  contradicting_evidence: LedgerEvidenceItem[];
  missing_reason: string | null;
  verification_method: string;
  created_at: string;
}

export interface ConditionVerdictResponse {
  task_id: string;
  items: ConditionVerdictItem[];
}

export interface EvidenceLedgerResponse {
  task_id: string;
  items: LedgerEvidenceItem[];
}

export interface QmdDocumentPreview {
  document_uri: string;
  document_title: string | null;
  collection: string | null;
  toc: Array<Record<string, unknown>>;
  summary: string | null;
  can_open: boolean;
  can_download: boolean;
}

export interface QmdEvidenceContext {
  document_uri: string;
  condition_id: string | null;
  page: number | null;
  anchor: string | null;
  text: string;
  source_tool: EvidenceSourceTool;
}
```

Extend `DocumentResultItem`:

```typescript
  decision_basis: Record<string, unknown>;
  uncertain_reasons: string[];
  evidence_support_rate: number;
  verification_status: VerificationStatus;
```

- [ ] **Step 4: Add frontend API client functions**

Modify imports in `frontend/src/lib/api.ts` to include new types, then append:

```typescript
export async function getConditionVerdicts(taskId: string): Promise<ConditionVerdictResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}/condition-verdicts`);
  return readJson<ConditionVerdictResponse>(response);
}

export async function getEvidenceLedger(taskId: string): Promise<EvidenceLedgerResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${pathSegment(taskId)}/evidence-ledger`);
  return readJson<EvidenceLedgerResponse>(response);
}

export async function getQmdPreview(documentUri: string): Promise<QmdDocumentPreview> {
  const search = new URLSearchParams({ document_uri: documentUri });
  const response = await fetch(`${apiBase}/api/qmd-documents/preview?${search.toString()}`);
  return readJson<QmdDocumentPreview>(response);
}

export async function getQmdEvidenceContext(params: { document_uri: string; condition_id?: string; page?: number | null }): Promise<QmdEvidenceContext> {
  const search = new URLSearchParams({ document_uri: params.document_uri });
  if (params.condition_id) search.set('condition_id', params.condition_id);
  if (params.page) search.set('page', String(params.page));
  const response = await fetch(`${apiBase}/api/qmd-documents/evidence-context?${search.toString()}`);
  return readJson<QmdEvidenceContext>(response);
}
```

- [ ] **Step 5: Load Phase 3 data in TaskProgressPage**

Modify imports in `frontend/src/pages/TaskProgressPage.tsx`:

```typescript
import { exportTaskUrl, getConditionVerdicts, getEvidenceLedger, getQmdEvidenceContext, getTaskResults, getTaskSummary, reviewDocumentResult } from '../lib/api';
import type { ConditionVerdictItem, DocumentResultItem, LedgerEvidenceItem, QmdEvidenceContext, ResultDecision, ReviewStatus, StreamEvent, TaskResults, TaskSummary } from '../lib/types';
```

Add state:

```typescript
const [verdicts, setVerdicts] = useState<ConditionVerdictItem[]>([]);
const [ledger, setLedger] = useState<LedgerEvidenceItem[]>([]);
const [previewContext, setPreviewContext] = useState<QmdEvidenceContext | null>(null);
```

Reset state inside the `useEffect` reset block:

```typescript
setVerdicts([]);
setLedger([]);
setPreviewContext(null);
```

Modify `loadFinal()`:

```typescript
const [nextSummary, nextResults, nextVerdicts, nextLedger] = await Promise.all([
  getTaskSummary(id),
  getTaskResults(id),
  getConditionVerdicts(id).catch(() => ({ task_id: id, items: [] })),
  getEvidenceLedger(id).catch(() => ({ task_id: id, items: [] }))
]);
if (isCancelled()) return;
setSummary(nextSummary);
setResults(nextResults);
setVerdicts(nextVerdicts.items);
setLedger(nextLedger.items);
```

Add helper inside component:

```typescript
async function handlePreviewEvidence(item: LedgerEvidenceItem) {
  try {
    const context = await getQmdEvidenceContext({
      document_uri: item.document_uri || item.artifact_ref || selectedDocument?.document_uri || '',
      condition_id: item.condition_id,
      page: item.page
    });
    setPreviewContext(context);
  } catch (err) {
    setError(err instanceof Error ? err.message : '加载原文上下文失败');
  }
}
```

Render Phase 3 sections below `ResultSummary`:

```tsx
<ConditionMatrix documents={filteredDocuments} verdicts={verdicts} onSelectDocument={setSelectedUri} />
<EvidenceLedgerPanel items={ledger.filter((item) => !selectedDocument || item.document_uri === selectedDocument.document_uri)} onPreview={handlePreviewEvidence} />
{previewContext ? (
  <section className="results-card evidence-context-card">
    <div className="section-title-row">
      <h2>原文上下文</h2>
      <span>{previewContext.source_tool}</span>
    </div>
    <p>{previewContext.text}</p>
  </section>
) : null}
```

Add components before `EvidencePanel`:

```tsx
function ConditionMatrix({ documents, verdicts, onSelectDocument }: { documents: DocumentResultItem[]; verdicts: ConditionVerdictItem[]; onSelectDocument: (uri: string) => void }) {
  const conditionIds = Array.from(new Set(verdicts.map((item) => item.condition_id)));
  return (
    <section className="results-card condition-matrix">
      <div className="section-title-row">
        <h2>条件矩阵</h2>
        <span>{conditionIds.length} 个条件</span>
      </div>
      {conditionIds.length === 0 ? (
        <p className="muted">暂无条件级核验结果</p>
      ) : (
        <div className="matrix-grid" style={{ gridTemplateColumns: `minmax(160px, 1.4fr) repeat(${conditionIds.length}, minmax(92px, 1fr))` }}>
          <strong>文档</strong>
          {conditionIds.map((id) => (
            <strong key={id}>{id}</strong>
          ))}
          {documents.map((document) => (
            <Fragment key={document.document_uri}>
              <button type="button" className="matrix-document" onClick={() => onSelectDocument(document.document_uri)}>
                {document.document_title || document.document_path}
              </button>
              {conditionIds.map((id) => {
                const verdict = verdicts.find((item) => item.document_uri === document.document_uri && item.condition_id === id);
                return (
                  <span className={`verdict-cell ${verdict?.verdict || 'unknown'}`} key={`${document.document_uri}-${id}`}>
                    {verdictLabel(verdict?.verdict || 'unknown')}
                  </span>
                );
              })}
            </Fragment>
          ))}
        </div>
      )}
    </section>
  );
}

function EvidenceLedgerPanel({ items, onPreview }: { items: LedgerEvidenceItem[]; onPreview: (item: LedgerEvidenceItem) => void }) {
  return (
    <section className="results-card evidence-ledger-card">
      <div className="section-title-row">
        <h2>证据账本</h2>
        <span>{items.length} 条证据</span>
      </div>
      {items.length === 0 ? (
        <p className="muted">暂无核验证据</p>
      ) : (
        items.map((item, index) => (
          <article className="ledger-item" key={`${item.document_uri}-${item.condition_id}-${index}`}>
            <div>
              <strong>{item.condition_id}</strong>
              <span>{item.role} · {item.source_tool}</span>
            </div>
            <p>{item.text}</p>
            <button className="mini-button" type="button" onClick={() => onPreview(item)}>
              预览原文
            </button>
          </article>
        ))
      )}
    </section>
  );
}

function verdictLabel(value: string): string {
  if (value === 'satisfied') return '满足';
  if (value === 'not_satisfied') return '不满足';
  if (value === 'conflicting') return '冲突';
  return '未知';
}
```

Add `Fragment` to the React import:

```typescript
import { Fragment, useEffect, useMemo, useState } from 'react';
```

- [ ] **Step 6: Add CSS**

Append to `frontend/src/styles/contract-agent.css`:

```css
.condition-matrix,
.evidence-ledger-card,
.evidence-context-card {
  margin-top: 16px;
}

.matrix-grid {
  display: grid;
  gap: 1px;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--border);
}

.matrix-grid > * {
  min-height: 38px;
  padding: 10px;
  background: var(--panel);
  font-size: 13px;
}

.matrix-document {
  border: 0;
  text-align: left;
  color: var(--text);
  cursor: pointer;
}

.verdict-cell {
  font-weight: 700;
}

.verdict-cell.satisfied {
  color: #137a3f;
}

.verdict-cell.not_satisfied {
  color: #9a3412;
}

.verdict-cell.conflicting {
  color: #b42318;
}

.verdict-cell.unknown {
  color: #6b7280;
}

.ledger-item {
  display: grid;
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
}

.ledger-item div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
```

- [ ] **Step 7: Add Phase 3 error copy**

Modify `frontend/src/lib/errorMessages.ts` by adding:

```typescript
  qmd_deep_read_unavailable: 'MinerU 文档内核验工具不可用。请检查 qmd MCP 是否启用了 doc_read/doc_grep/doc_query。',
  evidence_verification_failed: '候选合同已召回，但文档内证据核验失败。请检查 MinerU deep-read 服务和文档索引状态。',
  condition_verdict_invalid: '条件级判断结果格式不合法。请检查模型输出或结构化输出配置。',
  qmd_preview_unavailable: '暂时无法加载原文上下文，筛选结果仍可继续复核。',
  qmd_download_unavailable: '当前检索层未提供安全下载链接。',
  eval_dataset_invalid: '评测集格式不合法，请检查期望结果和文档 URI。',
  eval_run_failed: 'Agent 评测运行失败，请查看后端日志。'
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run phase3Api TaskProgressPage
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/pages/TaskProgressPage.tsx frontend/src/lib/errorMessages.ts frontend/src/styles/contract-agent.css frontend/tests/phase3Api.test.ts frontend/tests/TaskProgressPage.test.tsx
git commit -m "feat(frontend): show condition verdicts and evidence ledger"
```

---

### Task 8: Exports, Documentation, And Full Verification

**Files:**
- Modify: `backend/app/services/exports.py`
- Modify: `backend/tests/test_phase2_exports.py`
- Modify: `README.md`
- Create: `notes/phase-3-acceptance-checklist.md`

- [ ] **Step 1: Write failing export assertion**

In `backend/tests/test_phase2_exports.py`, extend the sample `ScreeningDocumentResult` with:

```python
decision_basis={"amount": "satisfied"},
uncertain_reasons=[],
evidence_support_rate=1.0,
verification_status="deep_read_verified",
```

Add assertions to the CSV/JSON tests:

```python
assert "verification_status" in csv_text
assert "evidence_support_rate" in csv_text
assert payload["results"][0]["verification_status"] == "deep_read_verified"
assert payload["results"][0]["decision_basis"] == {"amount": "satisfied"}
```

- [ ] **Step 2: Run export tests and verify they fail**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_exports.py -v
```

Expected: FAIL because exports do not include Phase 3 fields.

- [ ] **Step 3: Add Phase 3 fields to exports**

Modify `backend/app/services/exports.py`:

Add these headers to `EXPORT_FIELDS`:

```python
    "decision_basis",
    "uncertain_reasons",
    "evidence_support_rate",
    "verification_status",
```

Add Chinese labels:

```python
    "decision_basis": "条件级判断",
    "uncertain_reasons": "不确定原因",
    "evidence_support_rate": "证据支持率",
    "verification_status": "核验状态",
```

Add row values in the result row builder:

```python
        "decision_basis": _json_value(result.decision_basis),
        "uncertain_reasons": ",".join(result.uncertain_reasons or []),
        "evidence_support_rate": result.evidence_support_rate,
        "verification_status": result.verification_status,
```

Add this helper near the existing export formatting helpers:

```python
def _json_value(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
```

Add these fields to JSON result serialization:

```python
                "decision_basis": result.decision_basis,
                "uncertain_reasons": result.uncertain_reasons,
                "evidence_support_rate": result.evidence_support_rate,
                "verification_status": result.verification_status,
```

- [ ] **Step 4: Add README Phase 3 summary**

Append after README Phase 2 section:

```markdown
## Phase 3 可信证据能力

Phase 3 将合同筛选从“qmd 片段召回后文档级判断”升级为“候选召回后逐条件核验”。检索层继续固定使用 OpenDataLab MinerU-Document-Explorer，不建设上传、OCR、解析或索引闭环。

Phase 3 规划能力：

- ScreeningPlan 2.0：支持金额、日期、主体、条款存在/缺失、语义风险和关键词条件。
- MinerU deep-read 核验：在 qmd `query` 初筛后，使用文档内 grep/read/query/elements 能力确认上下文。
- 条件级 verdict：每份合同按条件输出满足、不满足、未知或冲突。
- 证据账本：区分召回片段、支持证据、反驳证据和缺失原因。
- 证据驱动预览：从证据跳转到原文上下文；下载仅在 qmd/MinerU 提供安全链接时开放。
- Agent 评测：使用 golden set 输出 precision、recall、uncertain rate 和 evidence support rate。
```

- [ ] **Step 5: Add acceptance checklist**

Create `notes/phase-3-acceptance-checklist.md`:

```markdown
# Phase 3 验收清单

日期：2026-06-24

Phase 3 验收可信证据筛选增强，不验收上传、OCR、解析、索引或 qmd 集合管理。

## 后端

- [ ] `ScreeningPlanPayload` 支持 v1 兼容和 v2 条件字段。
- [ ] `condition_verdicts` 可保存每个文档、每个条件的 verdict。
- [ ] `screening_document_results` 包含 `decision_basis`、`uncertain_reasons`、`evidence_support_rate`、`verification_status`。
- [ ] `QmdClient` 支持 `doc_toc`、`doc_grep`、`doc_read`、`doc_query`、`doc_elements`。
- [ ] qmd document URI 不允许路径逃逸。
- [ ] deep-read 失败时单文档降级为 `uncertain`，不强行入选。
- [ ] `/api/screening-tasks/{task_id}/condition-verdicts` 返回条件矩阵数据。
- [ ] `/api/screening-tasks/{task_id}/evidence-ledger` 返回证据账本。
- [ ] `/api/qmd-documents/preview` 可返回上下文摘要或明确错误。
- [ ] `/api/qmd-documents/download` 在无安全下载链接时返回 `qmd_download_unavailable`。
- [ ] `/api/agent-evals/run` 输出 precision、recall、uncertain rate、evidence support rate。

## 前端

- [ ] 任务详情页保留 Phase 2 三桶结果、复核和导出能力。
- [ ] 条件矩阵显示满足、不满足、未知、冲突。
- [ ] 证据账本显示证据角色和来源工具。
- [ ] 点击证据可加载原文上下文。
- [ ] 下载按钮只在后端声明可用时显示。
- [ ] `uncertain` 结果显示具体不确定原因。

## 回归

- [ ] `cd backend && ../.venv/bin/pytest`
- [ ] `cd frontend && npm test -- --run`
- [ ] `cd frontend && npm run build`
```

- [ ] **Step 6: Run full verification**

Run:

```bash
cd backend
../.venv/bin/pytest

cd ../frontend
npm test -- --run
npm run build
```

Expected: all commands PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/exports.py backend/tests/test_phase2_exports.py README.md notes/phase-3-acceptance-checklist.md
git commit -m "docs: add phase 3 acceptance notes"
```

---

## Self-Review

Spec coverage:

- ScreeningPlan 2.0: Task 1.
- qmd query plus MinerU deep-read: Tasks 3 and 4.
- Condition verdicts and document decision summary: Tasks 2 and 4.
- Evidence ledger APIs: Task 5.
- Evidence-driven preview and optional download: Task 5 and Task 7.
- Agent eval metrics: Task 6.
- Frontend condition matrix, ledger, uncertainty, preview: Task 7.
- Exports and acceptance documentation: Task 8.

Scope decisions:

- Upload, OCR, parsing, qmd indexing, and collection management remain out of scope.
- Existing `/api/contracts/{contract_id}/download` is not reused for qmd documents.
- Phase 2 result, review, history, SSE, and export behavior remains compatible.

Final verification command set:

```bash
cd backend
../.venv/bin/pytest

cd ../frontend
npm test -- --run
npm run build
```
