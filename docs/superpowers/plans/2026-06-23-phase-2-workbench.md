# Phase 2 Contract Screening Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 product workbench: task history, dynamic progress, document-level review, CSV/XLSX/JSON exports, read-only health summaries, and local worker stability.

**Architecture:** Extend the existing FastAPI/RQ/PostgreSQL backend without changing the Phase 1 qmd-first screening flow. Add review fields to document results, expose focused workbench APIs, and upgrade the React UI into a three-page workbench while preserving existing task creation, SSE, and result APIs. Keep the single-tenant internal model and do not add login or qmd collection management.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, RQ, PostgreSQL/SQLite tests, Pydantic, React, React Router, TypeScript, Vitest, Vite, qmd MCP, LangGraph/OpenAI-compatible LLM.

---

## File Structure

Backend:

- Modify `backend/app/enums.py`: add `ReviewStatus`, `WorkerMode`, and `AuditEventType.result_reviewed`.
- Modify `backend/app/models.py`: add review columns to `ScreeningDocumentResult`.
- Create `backend/alembic/versions/0003_phase2_workbench.py`: add review columns and indexes.
- Modify `backend/app/schemas.py`: add list, review, health, runtime, and export response schemas; extend `DocumentResultItem`.
- Modify `backend/app/api/screening_tasks.py`: add task list, copy task, review patch, and export endpoints.
- Create `backend/app/api/health.py`: expose `/api/qmd/status` and `/api/runtime/status`.
- Create `backend/app/services/exports.py`: build CSV, XLSX, and JSON exports from one task.
- Modify `backend/app/services/retrieval/qmd_client.py`: add a status normalization helper if tests show current raw shape is insufficient.
- Modify `backend/app/worker.py`: support `RQ_WORKER_MODE=simple|fork`, default to `simple` on macOS local runs.
- Modify `backend/app/config.py`: add `RQ_WORKER_MODE` setting and a redacted runtime diagnostic helper.
- Modify `backend/app/main.py`: register the new health router.
- Add backend tests in `backend/tests/test_phase2_workbench.py`, `backend/tests/test_phase2_exports.py`, `backend/tests/test_phase2_health_worker.py`.

Frontend:

- Modify `frontend/src/lib/types.ts`: add task list, review, health, runtime, and review fields.
- Modify `frontend/src/lib/api.ts`: add list, copy, review, export, qmd status, and runtime status clients.
- Modify `frontend/src/lib/sse.ts`: keep existing subscription shape; no protocol change.
- Create `frontend/src/lib/taskActivity.ts`: derive six progress stages and activity items from SSE events.
- Create `frontend/src/lib/reviewer.ts`: read/write reviewer name in `localStorage`.
- Modify `frontend/src/App.tsx`: add `/tasks` route.
- Modify `frontend/src/pages/UploadPage.tsx`: add health summary and recent tasks entry.
- Create `frontend/src/pages/TaskHistoryPage.tsx`: task list with filters and copy action.
- Modify `frontend/src/pages/TaskProgressPage.tsx`: dynamic progress, activity stream, result filters, review panel, export actions.
- Modify `frontend/src/styles/contract-agent.css`: workbench, history table/list, filters, activity stream, review panel, export controls.
- Add frontend tests in `frontend/tests/TaskHistoryPage.test.tsx`, update `TaskProgressPage.test.tsx`, `UploadPage.test.tsx`, and `api.test.ts`.

Documentation:

- Modify `README.md`: Phase 2 operation notes, worker mode, exports, and review model.
- Create or update `notes/phase-2-acceptance-checklist.md`: manual acceptance checklist.

---

### Task 1: Backend Review Model And Schemas

**Files:**
- Modify: `backend/app/enums.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/alembic/versions/0003_phase2_workbench.py`
- Test: `backend/tests/test_phase2_workbench.py`

- [ ] **Step 1: Write failing tests for review fields and migration text**

Add this file:

```python
# backend/tests/test_phase2_workbench.py
from uuid import uuid4

from sqlalchemy import inspect

from app.db import engine
from app.enums import ResultDecision, ReviewStatus
from app.models import ScreeningDocumentResult, ScreeningTask


def test_document_result_review_fields_default_to_unreviewed(db_session):
    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="GPU采购",
        raw_query="哪份合同采购了GPU服务器？",
        metrics={},
    )
    session.add(task)
    session.flush()
    result = ScreeningDocumentResult(
        task_id=task.id,
        document_uri="qmd://contract_docs/equipment-purchase-contract.md",
        document_path="equipment-purchase-contract.md",
        document_title="设备采购合同",
        collection="contract_docs",
        decision=ResultDecision.included.value,
        reason="Agent matched evidence",
        matched_conditions=["gpu_server_purchase"],
        missing_conditions=[],
        evidence=[],
        confidence=0.9,
    )
    session.add(result)
    session.commit()

    session.refresh(result)
    assert result.review_status == ReviewStatus.unreviewed.value
    assert result.review_decision is None
    assert result.review_note is None
    assert result.reviewer_name is None
    assert result.reviewed_at is None


def test_document_result_review_columns_exist_in_test_schema(db_session):
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("screening_document_results")}
    assert {"review_status", "review_decision", "review_note", "reviewer_name", "reviewed_at"} <= columns


def test_phase2_migration_adds_review_columns():
    migration = open("alembic/versions/0003_phase2_workbench.py", encoding="utf-8").read()
    assert "review_status" in migration
    assert "review_decision" in migration
    assert "review_note" in migration
    assert "reviewer_name" in migration
    assert "reviewed_at" in migration
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py -v
```

Expected: FAIL because `ReviewStatus`, model columns, and migration do not exist.

- [ ] **Step 3: Add enums**

Modify `backend/app/enums.py`:

```python
class ReviewStatus(StrEnum):
    unreviewed = "unreviewed"
    reviewed = "reviewed"


class WorkerMode(StrEnum):
    simple = "simple"
    fork = "fork"
```

Add to `AuditEventType`:

```python
    result_reviewed = "result_reviewed"
```

- [ ] **Step 4: Add model columns**

Modify `ScreeningDocumentResult` in `backend/app/models.py`:

```python
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    review_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Keep the existing unique constraint and decision index unchanged.

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/0003_phase2_workbench.py`:

```python
"""add phase 2 review fields

Revision ID: 0003_phase2_workbench
Revises: 0002_doc_results
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_phase2_workbench"
down_revision = "0002_doc_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("screening_document_results", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"))
    op.add_column("screening_document_results", sa.Column("review_decision", sa.String(length=32), nullable=True))
    op.add_column("screening_document_results", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("screening_document_results", sa.Column("reviewer_name", sa.String(length=128), nullable=True))
    op.add_column("screening_document_results", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_results_task_review", "screening_document_results", ["task_id", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_document_results_task_review", table_name="screening_document_results")
    op.drop_column("screening_document_results", "reviewed_at")
    op.drop_column("screening_document_results", "reviewer_name")
    op.drop_column("screening_document_results", "review_note")
    op.drop_column("screening_document_results", "review_decision")
    op.drop_column("screening_document_results", "review_status")
```

- [ ] **Step 6: Extend Pydantic schemas**

Modify imports in `backend/app/schemas.py`:

```python
from app.enums import ParseStatus, ResultDecision, ReviewStatus, TaskStatus
```

Add:

```python
class ReviewCounts(BaseModel):
    unreviewed: int
    reviewed: int


class ReviewResultRequest(BaseModel):
    review_status: Literal["reviewed"]
    review_decision: ResultDecision
    review_note: str | None = None
    reviewer_name: str = Field(min_length=1, max_length=128)


class ReviewResultResponse(BaseModel):
    result: "DocumentResultItem"
```

Extend `DocumentResultItem`:

```python
    result_id: UUID
    review_status: ReviewStatus = ReviewStatus.unreviewed
    review_decision: ResultDecision | None = None
    review_note: str | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
```

Use forward references only if the project’s Pydantic version requires them. If `ReviewResultResponse` is placed after `DocumentResultItem`, write it without quotes:

```python
class ReviewResultResponse(BaseModel):
    result: DocumentResultItem
```

- [ ] **Step 7: Update schema construction in `get_results`**

Modify the `DocumentResultItem(...)` construction in `backend/app/api/screening_tasks.py`:

```python
        item = DocumentResultItem(
            result_id=result.id,
            document_uri=result.document_uri,
            document_path=result.document_path,
            document_title=result.document_title,
            collection=result.collection,
            decision=ResultDecision(result.decision),
            reason=result.reason,
            matched_conditions=result.matched_conditions,
            missing_conditions=result.missing_conditions,
            evidence=[EvidenceItem(**e) for e in result.evidence],
            confidence=result.confidence,
            review_status=ReviewStatus(result.review_status),
            review_decision=ResultDecision(result.review_decision) if result.review_decision else None,
            review_note=result.review_note,
            reviewer_name=result.reviewer_name,
            reviewed_at=result.reviewed_at,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )
```

Add `ReviewStatus` to imports in that file.

- [ ] **Step 8: Run tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py tests/test_qmd_screening_flow.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/enums.py backend/app/models.py backend/app/schemas.py backend/app/api/screening_tasks.py backend/alembic/versions/0003_phase2_workbench.py backend/tests/test_phase2_workbench.py
git commit -m "feat: add document review fields"
```

---

### Task 2: Backend Task History And Copy APIs

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/api/screening_tasks.py`
- Test: `backend/tests/test_phase2_workbench.py`

- [ ] **Step 1: Add failing tests for task history**

Append to `backend/tests/test_phase2_workbench.py`:

```python
from app.enums import TaskStatus


def create_task(session, title, query, status=TaskStatus.completed.value):
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title=title,
        raw_query=query,
        status=status,
        current_stage=status,
        progress_percent=100 if status == TaskStatus.completed.value else 10,
        metrics={},
    )
    session.add(task)
    session.flush()
    return task


def test_list_tasks_filters_by_status_and_keyword(client, db_session):
    session, _ = db_session
    gpu_task = create_task(session, "GPU采购", "采购GPU服务器和存储服务器")
    create_task(session, "服务合同", "软件开发服务", TaskStatus.failed.value)
    session.add(
        ScreeningDocumentResult(
            task_id=gpu_task.id,
            document_uri="qmd://contract_docs/equipment-purchase-contract.md",
            document_path="equipment-purchase-contract.md",
            document_title="设备采购合同",
            collection="contract_docs",
            decision=ResultDecision.included.value,
            reason="matched",
            matched_conditions=["gpu"],
            missing_conditions=[],
            evidence=[],
            confidence=0.9,
            review_status=ReviewStatus.reviewed.value,
            review_decision=ResultDecision.included.value,
            reviewer_name="张三",
        )
    )
    session.commit()

    response = client.get("/api/screening-tasks?status=completed&q=GPU&sort=created_desc&limit=10&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["task_id"] == str(gpu_task.id)
    assert body["items"][0]["counts"]["included"] == 1
    assert body["items"][0]["review_counts"]["reviewed"] == 1
    assert body["items"][0]["review_counts"]["unreviewed"] == 0


def test_copy_task_creates_new_task_and_enqueues(client, db_session, monkeypatch):
    import app.api.screening_tasks as routes

    session, _ = db_session
    source = create_task(session, "GPU采购", "采购GPU服务器和存储服务器")
    session.commit()
    enqueued = []
    monkeypatch.setattr(routes, "enqueue_screening_task", lambda task_id: enqueued.append(str(task_id)) or f"job-{task_id}")

    response = client.post(f"/api/screening-tasks/{source.id}/copy")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] != str(source.id)
    assert body["raw_query"] == source.raw_query
    assert body["title"] == source.title
    assert len(enqueued) == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py::test_list_tasks_filters_by_status_and_keyword tests/test_phase2_workbench.py::test_copy_task_creates_new_task_and_enqueues -v
```

Expected: FAIL because list and copy endpoints do not exist.

- [ ] **Step 3: Add list schemas**

Add to `backend/app/schemas.py`:

```python
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
```

- [ ] **Step 4: Implement result count helper**

In `backend/app/api/screening_tasks.py`, add imports:

```python
from sqlalchemy import func, or_
from app.enums import ReviewStatus
from app.schemas import ReviewCounts, TaskListItem, TaskListResponse
```

Add helper:

```python
def task_counts_for_results(results: list[ScreeningDocumentResult]) -> tuple[TaskCounts, ReviewCounts]:
    counts = TaskCounts(
        documents=len(results),
        included=sum(1 for r in results if r.decision == ResultDecision.included.value),
        uncertain=sum(1 for r in results if r.decision == ResultDecision.uncertain.value),
        excluded=sum(1 for r in results if r.decision == ResultDecision.excluded.value),
    )
    review_counts = ReviewCounts(
        reviewed=sum(1 for r in results if r.review_status == ReviewStatus.reviewed.value),
        unreviewed=sum(1 for r in results if r.review_status == ReviewStatus.unreviewed.value),
    )
    return counts, review_counts
```

Update existing `task_summary()` to call the helper and return `counts`.

- [ ] **Step 5: Implement `GET /api/screening-tasks` before `/{task_id}`**

Add this route above `@router.get("/{task_id}")`:

```python
@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: str | None = None,
    q: str | None = None,
    sort: str = "created_desc",
    limit: int = 20,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    statement = select(ScreeningTask).where(ScreeningTask.owner_id == auth.owner_id)
    if status:
        if status == "active":
            statement = statement.where(ScreeningTask.status.in_([TaskStatus.uploaded.value, TaskStatus.retrieving.value, TaskStatus.classifying.value]))
        elif status in {item.value for item in TaskStatus}:
            statement = statement.where(ScreeningTask.status == status)
        else:
            raise ApiError("invalid_status", "Invalid task status filter", 400)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        statement = statement.where(or_(ScreeningTask.title.ilike(needle), ScreeningTask.raw_query.ilike(needle)))

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    if sort == "created_asc":
        statement = statement.order_by(ScreeningTask.created_at.asc())
    elif sort == "created_desc":
        statement = statement.order_by(ScreeningTask.created_at.desc())
    else:
        raise ApiError("invalid_sort", "Invalid task sort", 400)

    tasks = session.scalars(statement.limit(limit).offset(offset)).all()
    items = []
    for task in tasks:
        results = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).all()
        counts, review_counts = task_counts_for_results(results)
        items.append(
            TaskListItem(
                task_id=task.id,
                title=task.title,
                raw_query=task.raw_query,
                status=TaskStatus(task.status),
                progress_percent=task.progress_percent,
                current_stage=task.current_stage,
                error_code=task.error_code,
                error_message=task.error_message,
                created_at=task.created_at,
                updated_at=task.updated_at,
                completed_at=task.completed_at,
                counts=counts,
                review_counts=review_counts,
            )
        )
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)
```

- [ ] **Step 6: Implement `POST /copy` route before `/{task_id}`**

Add:

```python
@router.post("/{task_id}/copy", response_model=CreateTaskResponse)
def copy_task(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    source = load_owned_task(session, task_id, auth)
    task = ScreeningTask(
        owner_id=auth.owner_id,
        title=source.title,
        raw_query=source.raw_query,
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={"copied_from_task_id": str(source.id)},
    )
    session.add(task)
    session.flush()
    write_audit(session, AuditEventType.task_created.value, {"task_id": str(task.id), "title": task.title, "copied_from_task_id": str(source.id)}, actor_id=auth.owner_id, task=task)
    append_stream_event(session, task.id, "task_created", {"task_id": str(task.id), "title": task.title, "copied_from_task_id": str(source.id)})
    response_payload = CreateTaskResponse(task_id=task.id, title=task.title, raw_query=task.raw_query, status=TaskStatus(task.status), progress_percent=task.progress_percent, events_url=f"/api/screening-tasks/{task.id}/events", results_url=f"/api/screening-tasks/{task.id}/results")
    session.commit()
    try:
        rq_job_id = enqueue_screening_task(task.id)
    except Exception as exc:
        task = session.get(ScreeningTask, task.id)
        task.status = TaskStatus.failed.value
        task.current_stage = TaskStatus.failed.value
        task.error_code = "enqueue_failed"
        task.error_message = "Unable to enqueue screening task"
        task.completed_at = utcnow()
        write_audit(session, AuditEventType.task_failed.value, {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"}, actor_id=auth.owner_id, task=task)
        append_stream_event(session, task.id, "task_failed", {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"})
        session.commit()
        raise ApiError("enqueue_failed", "Unable to enqueue screening task", 503) from exc
    task = session.get(ScreeningTask, task.id)
    task.metrics = {**(task.metrics or {}), "rq_job_id": rq_job_id}
    session.commit()
    return response_payload
```

- [ ] **Step 7: Run backend tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py tests/test_qmd_screening_flow.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/api/screening_tasks.py backend/tests/test_phase2_workbench.py
git commit -m "feat: add task history and copy APIs"
```

---

### Task 3: Backend Result Review API

**Files:**
- Modify: `backend/app/api/screening_tasks.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_phase2_workbench.py`

- [ ] **Step 1: Add failing review endpoint tests**

Append to `backend/tests/test_phase2_workbench.py`:

```python
from app.models import AuditEvent


def test_review_document_result_records_manual_decision(client, db_session):
    session, _ = db_session
    task = create_task(session, "GPU采购", "采购GPU服务器")
    result = ScreeningDocumentResult(
        task_id=task.id,
        document_uri="qmd://contract_docs/equipment-purchase-contract.md",
        document_path="equipment-purchase-contract.md",
        document_title="设备采购合同",
        collection="contract_docs",
        decision=ResultDecision.uncertain.value,
        reason="Agent evidence was incomplete",
        matched_conditions=[],
        missing_conditions=["gpu"],
        evidence=[],
        confidence=0.4,
    )
    session.add(result)
    session.commit()

    response = client.patch(
        f"/api/screening-tasks/{task.id}/results/{result.id}/review",
        json={
            "review_status": "reviewed",
            "review_decision": "included",
            "review_note": "人工确认设备清单包含GPU服务器",
            "reviewer_name": "张三",
        },
    )

    assert response.status_code == 200
    body = response.json()["result"]
    assert body["decision"] == "uncertain"
    assert body["review_status"] == "reviewed"
    assert body["review_decision"] == "included"
    assert body["review_note"] == "人工确认设备清单包含GPU服务器"
    assert body["reviewer_name"] == "张三"
    assert body["reviewed_at"] is not None

    session.expire_all()
    stored = session.get(ScreeningDocumentResult, result.id)
    assert stored.decision == ResultDecision.uncertain.value
    assert stored.review_decision == ResultDecision.included.value

    audit = session.query(AuditEvent).filter_by(event_type="result_reviewed").one()
    assert audit.payload["result_id"] == str(result.id)
    assert audit.payload["review_decision"] == "included"


def test_review_result_rejects_result_from_other_task(client, db_session):
    session, _ = db_session
    task = create_task(session, "任务A", "A")
    other_task = create_task(session, "任务B", "B")
    result = ScreeningDocumentResult(
        task_id=other_task.id,
        document_uri="qmd://contract_docs/a.md",
        document_path="a.md",
        document_title="A",
        collection="contract_docs",
        decision=ResultDecision.excluded.value,
        reason="no match",
        matched_conditions=[],
        missing_conditions=["x"],
        evidence=[],
        confidence=0.2,
    )
    session.add(result)
    session.commit()

    response = client.patch(
        f"/api/screening-tasks/{task.id}/results/{result.id}/review",
        json={"review_status": "reviewed", "review_decision": "included", "review_note": "", "reviewer_name": "张三"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py::test_review_document_result_records_manual_decision tests/test_phase2_workbench.py::test_review_result_rejects_result_from_other_task -v
```

Expected: FAIL because review route does not exist.

- [ ] **Step 3: Add item builder helper**

In `backend/app/api/screening_tasks.py`, add:

```python
def document_result_item(result: ScreeningDocumentResult) -> DocumentResultItem:
    return DocumentResultItem(
        result_id=result.id,
        document_uri=result.document_uri,
        document_path=result.document_path,
        document_title=result.document_title,
        collection=result.collection,
        decision=ResultDecision(result.decision),
        reason=result.reason,
        matched_conditions=result.matched_conditions,
        missing_conditions=result.missing_conditions,
        evidence=[EvidenceItem(**e) for e in result.evidence],
        confidence=result.confidence,
        review_status=ReviewStatus(result.review_status),
        review_decision=ResultDecision(result.review_decision) if result.review_decision else None,
        review_note=result.review_note,
        reviewer_name=result.reviewer_name,
        reviewed_at=result.reviewed_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )
```

Refactor `get_results()` to call `document_result_item(result)`.

- [ ] **Step 4: Implement review endpoint**

Add imports:

```python
from app.schemas import ReviewResultRequest, ReviewResultResponse
```

Add route above events route:

```python
@router.patch("/{task_id}/results/{result_id}/review", response_model=ReviewResultResponse)
def review_result(task_id: UUID, result_id: UUID, payload: ReviewResultRequest, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    result = session.get(ScreeningDocumentResult, result_id)
    if result is None or result.task_id != task.id:
        raise ApiError("not_found", "Not found", 404)
    note = (payload.review_note or "").strip()
    reviewer = payload.reviewer_name.strip()
    result.review_status = ReviewStatus.reviewed.value
    result.review_decision = payload.review_decision.value
    result.review_note = note or None
    result.reviewer_name = reviewer
    result.reviewed_at = utcnow()
    write_audit(
        session,
        AuditEventType.result_reviewed.value,
        {
            "task_id": str(task.id),
            "result_id": str(result.id),
            "document_uri": result.document_uri,
            "agent_decision": result.decision,
            "review_decision": result.review_decision,
            "reviewer_name": reviewer,
        },
        actor_id=auth.owner_id,
        task=task,
    )
    session.commit()
    session.refresh(result)
    return ReviewResultResponse(result=document_result_item(result))
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_workbench.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/screening_tasks.py backend/app/schemas.py backend/tests/test_phase2_workbench.py
git commit -m "feat: add result review API"
```

---

### Task 4: Backend Export APIs

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/services/exports.py`
- Modify: `backend/app/api/screening_tasks.py`
- Test: `backend/tests/test_phase2_exports.py`

- [ ] **Step 1: Add failing export tests**

Create `backend/tests/test_phase2_exports.py`:

```python
import csv
import io
import json
from uuid import uuid4

from app.enums import ResultDecision, ReviewStatus, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask, StreamEvent


def seeded_export_task(session):
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="GPU采购",
        raw_query="哪份合同采购了GPU服务器和存储服务器？",
        status=TaskStatus.completed.value,
        current_stage=TaskStatus.completed.value,
        progress_percent=100,
        metrics={"qmd_result_count": 3},
    )
    session.add(task)
    session.flush()
    session.add(ScreeningPlan(task_id=task.id, plan_json={"conditions": [{"id": "gpu", "description": "采购GPU服务器"}]}))
    session.add(
        ScreeningDocumentResult(
            task_id=task.id,
            document_uri="qmd://contract_docs/equipment-purchase-contract.md",
            document_path="equipment-purchase-contract.md",
            document_title="设备采购合同",
            collection="contract_docs",
            decision=ResultDecision.included.value,
            reason="Agent matched",
            matched_conditions=["gpu"],
            missing_conditions=[],
            evidence=[{"page": 1, "text": "GPU服务器 4台", "source": "qmd", "score": 0.93, "condition_id": "gpu", "artifact_ref": "qmd://contract_docs/equipment-purchase-contract.md"}],
            confidence=0.9,
            review_status=ReviewStatus.reviewed.value,
            review_decision=ResultDecision.included.value,
            review_note="人工确认",
            reviewer_name="张三",
        )
    )
    session.add(StreamEvent(task_id=task.id, sequence=1, event_type="task_created", payload={"task_id": str(task.id)}))
    session.commit()
    return task


def test_export_csv_contains_business_columns(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["task_title"] == "GPU采购"
    assert rows[0]["agent_decision"] == "included"
    assert rows[0]["review_decision"] == "included"
    assert rows[0]["reviewer_name"] == "张三"
    assert "GPU服务器 4台" in rows[0]["evidence_summary"]


def test_export_json_contains_task_plan_results_events(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == str(task.id)
    assert payload["plan"]["conditions"][0]["id"] == "gpu"
    assert payload["results"][0]["reviewer_name"] == "张三"
    assert payload["events"][0]["type"] == "task_created"


def test_export_xlsx_returns_excel_content_type(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content.startswith(b"PK")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_exports.py -v
```

Expected: FAIL because export endpoints and service do not exist.

- [ ] **Step 3: Add XLSX dependency**

Modify `backend/pyproject.toml` dependencies:

```toml
  "openpyxl>=3.1,<4",
```

Then install/update local environment:

```bash
cd backend
../.venv/bin/python -m pip install -e .
```

Expected: package install succeeds and `python -c "import openpyxl"` succeeds.

- [ ] **Step 4: Create export service**

Create `backend/app/services/exports.py`:

```python
import csv
import io
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask, StreamEvent


EXPORT_COLUMNS = [
    "task_id",
    "task_title",
    "raw_query",
    "task_created_at",
    "task_completed_at",
    "document_uri",
    "document_path",
    "document_title",
    "collection",
    "agent_decision",
    "agent_reason",
    "confidence",
    "matched_conditions",
    "missing_conditions",
    "review_status",
    "review_decision",
    "review_note",
    "reviewer_name",
    "reviewed_at",
    "evidence_summary",
]


def _value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def evidence_summary(evidence: list[dict[str, Any]]) -> str:
    parts = []
    for item in evidence:
        text = str(item.get("text", "")).replace("\n", " ").strip()
        condition_id = item.get("condition_id") or ""
        score = item.get("score")
        parts.append(f"{condition_id} score={score}: {text}")
    return " | ".join(parts)


def export_rows(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> list[dict[str, str]]:
    rows = []
    for result in results:
        rows.append(
            {
                "task_id": str(task.id),
                "task_title": task.title,
                "raw_query": task.raw_query,
                "task_created_at": _value(task.created_at),
                "task_completed_at": _value(task.completed_at),
                "document_uri": result.document_uri,
                "document_path": result.document_path,
                "document_title": result.document_title or "",
                "collection": result.collection,
                "agent_decision": result.decision,
                "agent_reason": result.reason,
                "confidence": _value(result.confidence),
                "matched_conditions": _value(result.matched_conditions),
                "missing_conditions": _value(result.missing_conditions),
                "review_status": result.review_status,
                "review_decision": result.review_decision or "",
                "review_note": result.review_note or "",
                "reviewer_name": result.reviewer_name or "",
                "reviewed_at": _value(result.reviewed_at),
                "evidence_summary": evidence_summary(result.evidence or []),
            }
        )
    return rows


def build_csv(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(export_rows(task, results))
    return buffer.getvalue()


def build_xlsx(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Screening Results"
    sheet.append(EXPORT_COLUMNS)
    for row in export_rows(task, results):
        sheet.append([row[column] for column in EXPORT_COLUMNS])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_json(session: Session, task: ScreeningTask, results: list[ScreeningDocumentResult]) -> dict[str, Any]:
    plan = session.scalars(select(ScreeningPlan).where(ScreeningPlan.task_id == task.id)).first()
    events = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence)).all()
    return {
        "task": {
            "task_id": str(task.id),
            "title": task.title,
            "raw_query": task.raw_query,
            "status": task.status,
            "progress_percent": task.progress_percent,
            "current_stage": task.current_stage,
            "error_code": task.error_code,
            "error_message": task.error_message,
            "metrics": task.metrics,
            "created_at": _value(task.created_at),
            "updated_at": _value(task.updated_at),
            "completed_at": _value(task.completed_at),
        },
        "plan": plan.plan_json if plan else None,
        "results": [
            {
                "result_id": str(result.id),
                "document_uri": result.document_uri,
                "document_path": result.document_path,
                "document_title": result.document_title,
                "collection": result.collection,
                "decision": result.decision,
                "reason": result.reason,
                "matched_conditions": result.matched_conditions,
                "missing_conditions": result.missing_conditions,
                "evidence": result.evidence,
                "confidence": result.confidence,
                "review_status": result.review_status,
                "review_decision": result.review_decision,
                "review_note": result.review_note,
                "reviewer_name": result.reviewer_name,
                "reviewed_at": _value(result.reviewed_at),
            }
            for result in results
        ],
        "events": [
            {
                "sequence": event.sequence,
                "type": event.event_type,
                "payload": event.payload,
                "created_at": _value(event.created_at),
            }
            for event in events
        ],
    }
```

- [ ] **Step 5: Add export endpoints**

In `backend/app/api/screening_tasks.py`, add imports:

```python
from fastapi.responses import Response, JSONResponse
from app.services.exports import build_csv, build_json, build_xlsx
```

Add helper:

```python
def load_task_results(session: Session, task: ScreeningTask) -> list[ScreeningDocumentResult]:
    return session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id).order_by(ScreeningDocumentResult.decision, ScreeningDocumentResult.document_path)).all()
```

Add routes before `/{task_id}/events`:

```python
@router.get("/{task_id}/export.csv")
def export_csv(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    csv_text = build_csv(task, load_task_results(session, task))
    return Response(content=csv_text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="screening-{task.id}.csv"'})


@router.get("/{task_id}/export.xlsx")
def export_xlsx(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    content = build_xlsx(task, load_task_results(session, task))
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="screening-{task.id}.xlsx"'})


@router.get("/{task_id}/export.json")
def export_json(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    return JSONResponse(build_json(session, task, load_task_results(session, task)))
```

- [ ] **Step 6: Run export tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_exports.py -v
```

Expected: PASS.

- [ ] **Step 7: Run full backend tests**

Run:

```bash
cd backend
../.venv/bin/pytest
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app/services/exports.py backend/app/api/screening_tasks.py backend/tests/test_phase2_exports.py
git commit -m "feat: add screening result exports"
```

---

### Task 5: Health APIs And Worker Mode

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/worker.py`
- Create: `backend/app/api/health.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_phase2_health_worker.py`

- [ ] **Step 1: Add failing health and worker tests**

Create `backend/tests/test_phase2_health_worker.py`:

```python
import sys

from app.config import Settings


def test_runtime_status_redacts_llm_key(client):
    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["has_api_key"] is True
    assert "api_key" not in body["llm"]
    assert body["worker"]["mode"] in {"simple", "fork"}


def test_qmd_status_reports_configured_collections(client, monkeypatch):
    import app.api.health as health

    class HealthyQmd:
        def status(self):
            return {"collections": [{"name": "contract_docs", "files": 3}]}

    monkeypatch.setattr(health, "QmdClient", lambda: HealthyQmd())
    monkeypatch.setattr(health.settings, "QMD_COLLECTIONS", "contract_docs")

    response = client.get("/api/qmd/status")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["collections"][0]["name"] == "contract_docs"
    assert body["collections"][0]["exists"] is True
    assert body["collections"][0]["document_count"] == 3


def test_worker_mode_defaults_to_simple_on_macos(monkeypatch):
    from app.worker import choose_worker_class
    from rq import SimpleWorker

    monkeypatch.setattr(sys, "platform", "darwin")
    assert choose_worker_class("auto") is SimpleWorker


def test_worker_mode_can_choose_fork(monkeypatch):
    from app.worker import choose_worker_class
    from rq import Worker

    monkeypatch.setattr(sys, "platform", "darwin")
    assert choose_worker_class("fork") is Worker
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_health_worker.py -v
```

Expected: FAIL because routes and worker mode helpers do not exist.

- [ ] **Step 3: Add config settings and diagnostics**

Modify `backend/app/config.py`:

```python
    RQ_WORKER_MODE: str = "auto"
```

Add validator:

```python
    @field_validator("RQ_WORKER_MODE")
    @classmethod
    def validate_rq_worker_mode(cls, value: str) -> str:
        value = value.strip()
        if value not in {"auto", "simple", "fork"}:
            raise ValueError("RQ_WORKER_MODE must be auto, simple, or fork")
        return value
```

Add method:

```python
    def redacted_runtime_status(self) -> dict:
        return {
            "env_file": str(PROJECT_ENV_FILE),
            "llm": {
                "base_url": self.AGENT_LLM_BASE_URL,
                "model": self.AGENT_LLM_MODEL,
                "has_api_key": bool(self.AGENT_LLM_API_KEY),
                "api_key_length": len(self.AGENT_LLM_API_KEY),
            },
            "qmd": {
                "backend": self.QMD_BACKEND,
                "url": self.QMD_MCP_URL,
                "collections": [item.strip() for item in self.QMD_COLLECTIONS.split(",") if item.strip()],
            },
            "redis": {"url": self.REDIS_URL},
            "worker": {"mode": self.RQ_WORKER_MODE},
        }
```

- [ ] **Step 4: Add health router**

Create `backend/app/api/health.py`:

```python
from fastapi import APIRouter

from app.config import settings
from app.services.retrieval.qmd_client import QmdClient

router = APIRouter()


@router.get("/runtime/status")
def runtime_status():
    return settings.redacted_runtime_status()


@router.get("/qmd/status")
def qmd_status():
    configured = [item.strip() for item in settings.QMD_COLLECTIONS.split(",") if item.strip()]
    try:
        status = QmdClient().status()
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "collections": [{"name": name, "exists": False, "document_count": 0} for name in configured],
        }
    raw_collections = status.get("collections", []) if isinstance(status, dict) else []
    by_name = {item.get("name"): item for item in raw_collections if isinstance(item, dict)}
    collections = []
    for name in configured:
        item = by_name.get(name)
        collections.append(
            {
                "name": name,
                "exists": item is not None,
                "document_count": int(item.get("files", 0)) if item else 0,
            }
        )
    return {"available": True, "collections": collections}
```

Modify `backend/app/main.py` imports:

```python
    from app.api import contracts, health, screening_tasks
```

Register:

```python
    app.include_router(health.router, prefix="/api", tags=["health"])
```

- [ ] **Step 5: Add worker mode selection**

Modify `backend/app/worker.py`:

```python
import sys

from redis import Redis
from rq import SimpleWorker, Worker

from app.config import settings


def choose_worker_class(mode: str):
    if mode == "simple":
        return SimpleWorker
    if mode == "fork":
        return Worker
    if sys.platform == "darwin":
        return SimpleWorker
    return Worker


def main() -> None:
    worker_class = choose_worker_class(settings.RQ_WORKER_MODE)
    diagnostics = settings.redacted_runtime_status()
    print(
        {
            "worker_mode": worker_class.__name__,
            "env_file": diagnostics["env_file"],
            "llm_has_api_key": diagnostics["llm"]["has_api_key"],
            "llm_model": diagnostics["llm"]["model"],
            "qmd_url": diagnostics["qmd"]["url"],
            "qmd_collections": diagnostics["qmd"]["collections"],
            "redis_url": diagnostics["redis"]["url"],
        }
    )
    worker = worker_class(["screening"], connection=Redis.from_url(settings.REDIS_URL))
    worker.work()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run health tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_phase2_health_worker.py tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/worker.py backend/app/api/health.py backend/app/main.py backend/tests/test_phase2_health_worker.py
git commit -m "feat: add health status and local worker mode"
```

---

### Task 6: Frontend API Types And Clients

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/tests/api.test.ts`

- [ ] **Step 1: Add failing API client tests**

Extend `frontend/tests/api.test.ts`:

```typescript
import {
  copyScreeningTask,
  exportTaskUrl,
  getQmdStatus,
  getRuntimeStatus,
  listScreeningTasks,
  reviewDocumentResult
} from '../src/lib/api';

it('lists screening tasks with filters', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  await listScreeningTasks({ status: 'completed', q: 'GPU', sort: 'created_desc', limit: 20, offset: 0 });

  expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks?status=completed&q=GPU&sort=created_desc&limit=20&offset=0');
});

it('copies screening tasks', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: 'task-2' }), { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  await copyScreeningTask('task-1');

  expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/copy', { method: 'POST' });
});

it('reviews document results', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ result: { result_id: 'result-1' } }), { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  await reviewDocumentResult('task-1', 'result-1', {
    review_status: 'reviewed',
    review_decision: 'included',
    review_note: '人工确认',
    reviewer_name: '张三'
  });

  expect(fetchMock).toHaveBeenCalledWith('/api/screening-tasks/task-1/results/result-1/review', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      review_status: 'reviewed',
      review_decision: 'included',
      review_note: '人工确认',
      reviewer_name: '张三'
    })
  });
});

it('builds export URLs and loads health statuses', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ available: true }), { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  expect(exportTaskUrl('task-1', 'csv')).toBe('/api/screening-tasks/task-1/export.csv');
  await getQmdStatus();
  await getRuntimeStatus();

  expect(fetchMock).toHaveBeenCalledWith('/api/qmd/status');
  expect(fetchMock).toHaveBeenCalledWith('/api/runtime/status');
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run tests/api.test.ts
```

Expected: FAIL because clients and types do not exist.

- [ ] **Step 3: Extend frontend types**

Add to `frontend/src/lib/types.ts`:

```typescript
export type ReviewStatus = 'unreviewed' | 'reviewed';
export type TaskListStatusFilter = 'all' | 'active' | TaskStatus;
export type TaskSort = 'created_desc' | 'created_asc';
export type ExportFormat = 'csv' | 'xlsx' | 'json';

export interface ReviewCounts {
  unreviewed: number;
  reviewed: number;
}

export interface TaskListItem extends TaskSummary {
  review_counts: ReviewCounts;
}

export interface TaskListResponse {
  items: TaskListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaskListParams {
  status?: TaskListStatusFilter;
  q?: string;
  sort?: TaskSort;
  limit?: number;
  offset?: number;
}

export interface ReviewResultRequest {
  review_status: 'reviewed';
  review_decision: ResultDecision;
  review_note?: string;
  reviewer_name: string;
}

export interface ReviewResultResponse {
  result: DocumentResultItem;
}

export interface QmdCollectionStatus {
  name: string;
  exists: boolean;
  document_count: number;
}

export interface QmdStatus {
  available: boolean;
  error?: string;
  collections: QmdCollectionStatus[];
}

export interface RuntimeStatus {
  env_file: string;
  llm: { base_url: string; model: string; has_api_key: boolean; api_key_length: number };
  qmd: { backend: string; url: string; collections: string[] };
  redis: { url: string };
  worker: { mode: string };
}
```

Extend `DocumentResultItem`:

```typescript
  result_id: string;
  review_status: ReviewStatus;
  review_decision: ResultDecision | null;
  review_note: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
```

- [ ] **Step 4: Add API clients**

Modify `frontend/src/lib/api.ts` imports:

```typescript
import type {
  CreateTaskRequest,
  CreateTaskResponse,
  ExportFormat,
  QmdStatus,
  ReviewResultRequest,
  ReviewResultResponse,
  RuntimeStatus,
  TaskListParams,
  TaskListResponse,
  TaskResults,
  TaskSummary
} from './types';
```

Add:

```typescript
function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== 'all') search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

export async function listScreeningTasks(params: TaskListParams = {}): Promise<TaskListResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks${buildQuery(params)}`);
  return readJson<TaskListResponse>(response);
}

export async function copyScreeningTask(taskId: string): Promise<CreateTaskResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${taskId}/copy`, { method: 'POST' });
  return readJson<CreateTaskResponse>(response);
}

export async function reviewDocumentResult(taskId: string, resultId: string, payload: ReviewResultRequest): Promise<ReviewResultResponse> {
  const response = await fetch(`${apiBase}/api/screening-tasks/${taskId}/results/${resultId}/review`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readJson<ReviewResultResponse>(response);
}

export function exportTaskUrl(taskId: string, format: ExportFormat): string {
  return `${apiBase}/api/screening-tasks/${taskId}/export.${format}`;
}

export async function getQmdStatus(): Promise<QmdStatus> {
  const response = await fetch(`${apiBase}/api/qmd/status`);
  return readJson<QmdStatus>(response);
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  const response = await fetch(`${apiBase}/api/runtime/status`);
  return readJson<RuntimeStatus>(response);
}
```

- [ ] **Step 5: Run frontend API tests**

Run:

```bash
cd frontend
npm test -- --run tests/api.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/tests/api.test.ts
git commit -m "feat: add workbench API clients"
```

---

### Task 7: Frontend Task Activity Derivation

**Files:**
- Create: `frontend/src/lib/taskActivity.ts`
- Test: `frontend/tests/taskActivity.test.ts`

- [ ] **Step 1: Write failing activity derivation tests**

Create `frontend/tests/taskActivity.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { buildTaskActivity } from '../src/lib/taskActivity';
import type { StreamEvent, TaskSummary } from '../src/lib/types';

const baseSummary: TaskSummary = {
  task_id: 'task-1',
  title: 'GPU采购',
  raw_query: '采购GPU服务器',
  status: 'classifying',
  progress_percent: 85,
  current_stage: 'classifying',
  error_code: null,
  error_message: null,
  created_at: '2026-06-23T00:00:00Z',
  updated_at: '2026-06-23T00:00:00Z',
  completed_at: null,
  counts: { documents: 0, included: 0, uncertain: 0, excluded: 0 }
};

function event(type: string, payload: Record<string, unknown>): StreamEvent {
  return { event_id: `task-1:${type}`, type, task_id: 'task-1', timestamp: '2026-06-23T00:00:00Z', payload };
}

describe('buildTaskActivity', () => {
  it('maps SSE events into six stages and activity text', () => {
    const activity = buildTaskActivity(baseSummary, [
      event('task_created', { title: 'GPU采购' }),
      event('criteria_parsed', { conditions: [{ id: 'gpu', description: '采购GPU服务器' }] }),
      event('qmd_checking', { collections: ['contract_docs'] }),
      event('qmd_searching', { query_text: 'GPU服务器采购', condition_id: 'gpu' }),
      event('qmd_retrieved', { query_text: 'GPU服务器采购', candidate_count: 3 }),
      event('document_classified', { document_path: 'equipment.md', decision: 'included' })
    ]);

    expect(activity.stages.map((stage) => stage.label)).toEqual(['提交任务', '理解筛选条件', '检查合同集合', '检索证据', '分析文档', '生成结果']);
    expect(activity.stages.find((stage) => stage.key === 'retrieve')?.state).toBe('done');
    expect(activity.stages.find((stage) => stage.key === 'classify')?.state).toBe('active');
    expect(activity.items.map((item) => item.text)).toContain('已解析 1 个筛选条件');
    expect(activity.items.map((item) => item.text)).toContain('正在检索 GPU服务器采购');
    expect(activity.items.map((item) => item.text)).toContain('返回 3 条候选');
  });

  it('marks terminal failure stage from summary', () => {
    const activity = buildTaskActivity({ ...baseSummary, status: 'failed', error_code: 'qmd_unavailable', error_message: 'Unable to reach qmd' }, []);
    expect(activity.stages.some((stage) => stage.state === 'failed')).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run tests/taskActivity.test.ts
```

Expected: FAIL because `taskActivity.ts` does not exist.

- [ ] **Step 3: Implement task activity derivation**

Create `frontend/src/lib/taskActivity.ts`:

```typescript
import type { StreamEvent, TaskSummary } from './types';

export type StageState = 'pending' | 'active' | 'done' | 'failed';

export interface TaskStage {
  key: 'submit' | 'plan' | 'check' | 'retrieve' | 'classify' | 'complete';
  label: string;
  state: StageState;
}

export interface ActivityItem {
  id: string;
  type: string;
  text: string;
  timestamp: string;
}

const STAGES: Omit<TaskStage, 'state'>[] = [
  { key: 'submit', label: '提交任务' },
  { key: 'plan', label: '理解筛选条件' },
  { key: 'check', label: '检查合同集合' },
  { key: 'retrieve', label: '检索证据' },
  { key: 'classify', label: '分析文档' },
  { key: 'complete', label: '生成结果' }
];

const EVENT_STAGE: Record<string, TaskStage['key']> = {
  task_created: 'submit',
  task_started: 'submit',
  criteria_parsed: 'plan',
  qmd_checking: 'check',
  qmd_searching: 'retrieve',
  qmd_retrieved: 'retrieve',
  document_classified: 'classify',
  progress: 'classify',
  task_completed: 'complete',
  task_failed: 'complete'
};

function activityText(event: StreamEvent): string {
  if (event.type === 'task_created') return '任务已创建';
  if (event.type === 'task_started') return 'worker 已接收任务';
  if (event.type === 'criteria_parsed') {
    const conditions = Array.isArray(event.payload.conditions) ? event.payload.conditions.length : 0;
    return `已解析 ${conditions} 个筛选条件`;
  }
  if (event.type === 'qmd_checking') return `正在检查合同集合 ${(event.payload.collections as string[] | undefined)?.join(', ') || ''}`.trim();
  if (event.type === 'qmd_searching') return `正在检索 ${String(event.payload.query_text || '')}`.trim();
  if (event.type === 'qmd_retrieved') return `返回 ${Number(event.payload.candidate_count || 0)} 条候选`;
  if (event.type === 'document_classified') return `${String(event.payload.document_path || event.payload.document_uri || '文档')} 判断为 ${String(event.payload.decision || '')}`.trim();
  if (event.type === 'progress') return `已分析 ${Number(event.payload.reviewed || 0)} 份文档`;
  if (event.type === 'task_completed') return '任务已生成结果';
  if (event.type === 'task_failed') return `任务失败：${String(event.payload.error_code || 'unknown')}`;
  return event.type;
}

export function buildTaskActivity(summary: TaskSummary | null, events: StreamEvent[]) {
  const reached = new Set<TaskStage['key']>();
  events.forEach((event) => {
    const stage = EVENT_STAGE[event.type];
    if (stage) reached.add(stage);
  });
  if (summary?.status === 'completed') reached.add('complete');

  let activeKey: TaskStage['key'] = 'submit';
  for (const event of events) {
    const stage = EVENT_STAGE[event.type];
    if (stage) activeKey = stage;
  }
  if (summary?.status === 'completed') activeKey = 'complete';

  const activeIndex = STAGES.findIndex((stage) => stage.key === activeKey);
  const stages = STAGES.map((stage, index): TaskStage => {
    if (summary?.status === 'failed' && index === Math.max(0, activeIndex)) return { ...stage, state: 'failed' };
    if (summary?.status === 'completed') return { ...stage, state: 'done' };
    if (index < activeIndex || reached.has(stage.key)) return { ...stage, state: index === activeIndex ? 'active' : 'done' };
    if (index === activeIndex) return { ...stage, state: 'active' };
    return { ...stage, state: 'pending' };
  });

  return {
    stages,
    items: events.map((event): ActivityItem => ({ id: event.event_id, type: event.type, text: activityText(event), timestamp: event.timestamp }))
  };
}
```

- [ ] **Step 4: Run activity tests**

Run:

```bash
cd frontend
npm test -- --run tests/taskActivity.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/taskActivity.ts frontend/tests/taskActivity.test.ts
git commit -m "feat: derive task activity timeline"
```

---

### Task 8: Frontend History Page And Home Health Summary

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/UploadPage.tsx`
- Create: `frontend/src/pages/TaskHistoryPage.tsx`
- Modify: `frontend/src/styles/contract-agent.css`
- Test: `frontend/tests/TaskHistoryPage.test.tsx`
- Test: `frontend/tests/UploadPage.test.tsx`

- [ ] **Step 1: Add failing history page test**

Create `frontend/tests/TaskHistoryPage.test.tsx`:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TaskHistoryPage } from '../src/pages/TaskHistoryPage';

describe('TaskHistoryPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders task list filters and copies a task', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                task_id: 'task-1',
                title: 'GPU采购',
                raw_query: '采购GPU服务器',
                status: 'completed',
                progress_percent: 100,
                current_stage: 'completed',
                error_code: null,
                error_message: null,
                created_at: '2026-06-23T00:00:00Z',
                updated_at: '2026-06-23T00:00:00Z',
                completed_at: '2026-06-23T00:01:00Z',
                counts: { documents: 3, included: 1, uncertain: 2, excluded: 0 },
                review_counts: { reviewed: 1, unreviewed: 2 }
              }
            ],
            total: 1,
            limit: 20,
            offset: 0
          }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ task_id: 'task-2' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={['/tasks']}>
        <Routes>
          <Route path="/tasks" element={<TaskHistoryPage />} />
          <Route path="/tasks/:taskId" element={<div>copied task</div>} />
        </Routes>
      </MemoryRouter>
    );

    expect(await screen.findByText('GPU采购')).toBeInTheDocument();
    expect(screen.getByText('1 / 3 已复核')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '复制任务' }));

    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith('/api/screening-tasks/task-1/copy', { method: 'POST' }));
  });
});
```

- [ ] **Step 2: Update home page test expectation**

In `frontend/tests/UploadPage.test.tsx`, add assertions after render:

```typescript
expect(screen.getByText('当前合同集合')).toBeInTheDocument();
expect(screen.getByRole('link', { name: '查看任务历史' })).toBeInTheDocument();
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run tests/TaskHistoryPage.test.tsx tests/UploadPage.test.tsx
```

Expected: FAIL because history page and home health summary do not exist.

- [ ] **Step 4: Add route**

Modify `frontend/src/App.tsx`:

```tsx
import { TaskHistoryPage } from './pages/TaskHistoryPage';
```

Add route:

```tsx
<Route path="/tasks" element={<TaskHistoryPage />} />
```

- [ ] **Step 5: Implement history page**

Create `frontend/src/pages/TaskHistoryPage.tsx`:

```tsx
import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { copyScreeningTask, listScreeningTasks } from '../lib/api';
import type { TaskListItem, TaskListResponse, TaskListStatusFilter, TaskSort } from '../lib/types';

const statusLabels: Record<string, string> = {
  all: '全部',
  active: '处理中',
  completed: '完成',
  failed: '失败'
};

export function TaskHistoryPage() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskListResponse | null>(null);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<TaskListStatusFilter>('all');
  const [sort, setSort] = useState<TaskSort>('created_desc');
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      setTasks(await listScreeningTasks({ q, status, sort, limit: 20, offset: 0 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载任务历史失败');
    }
  }

  useEffect(() => {
    void load();
  }, [status, sort]);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    await load();
  }

  async function handleCopy(task: TaskListItem) {
    const copied = await copyScreeningTask(task.task_id);
    navigate(`/tasks/${copied.task_id}`);
  }

  return (
    <main className="agent-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">TASKS</p>
          <h1>任务历史</h1>
          <p className="topbar-subtitle">搜索、筛选并复用历史筛选任务。</p>
        </div>
        <Link className="ghost-button" to="/">
          新建筛选
        </Link>
      </header>
      <section className="history-toolbar">
        <form onSubmit={handleSearch}>
          <input aria-label="搜索任务" value={q} onChange={(event) => setQ(event.currentTarget.value)} placeholder="搜索标题或筛选条件" />
          <button className="primary-button" type="submit">搜索</button>
        </form>
        <select aria-label="任务状态" value={status} onChange={(event) => setStatus(event.currentTarget.value as TaskListStatusFilter)}>
          {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select aria-label="时间排序" value={sort} onChange={(event) => setSort(event.currentTarget.value as TaskSort)}>
          <option value="created_desc">最新优先</option>
          <option value="created_asc">最早优先</option>
        </select>
      </section>
      {error ? <p className="error-text">{error}</p> : null}
      <section className="history-list">
        {(tasks?.items || []).map((task) => (
          <article className="history-row" key={task.task_id}>
            <div>
              <span className={`match-pill ${task.status === 'completed' ? 'full' : task.status === 'failed' ? 'none' : 'review'}`}>{task.status}</span>
              <h2>{task.title}</h2>
              <p>{task.raw_query}</p>
              <small>{new Date(task.created_at).toLocaleString()}</small>
            </div>
            <div className="history-metrics">
              <span>{task.counts.included} 入选</span>
              <span>{task.counts.uncertain} 需确认</span>
              <span>{task.review_counts.reviewed} / {task.counts.documents} 已复核</span>
            </div>
            <div className="history-actions">
              <Link className="mini-button" to={`/tasks/${task.task_id}`}>查看详情</Link>
              <button className="mini-button" type="button" onClick={() => void handleCopy(task)}>复制任务</button>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
```

- [ ] **Step 6: Add home health summary**

Modify `frontend/src/pages/UploadPage.tsx` imports:

```tsx
import { Link } from 'react-router-dom';
import { getQmdStatus, getRuntimeStatus } from '../lib/api';
import type { QmdStatus, RuntimeStatus } from '../lib/types';
import { useEffect, useState } from 'react';
```

Keep existing `FormEvent` import by combining React imports:

```tsx
import { FormEvent, useEffect, useState } from 'react';
```

Add state:

```tsx
const [qmdStatus, setQmdStatus] = useState<QmdStatus | null>(null);
const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
```

Add effect:

```tsx
useEffect(() => {
  void Promise.all([getQmdStatus(), getRuntimeStatus()]).then(([qmd, runtime]) => {
    setQmdStatus(qmd);
    setRuntimeStatus(runtime);
  }).catch(() => {
    setQmdStatus(null);
    setRuntimeStatus(null);
  });
}, []);
```

Add inside the center panel before the workflow summary:

```tsx
<section className="summary-card">
  <div>
    <p className="eyebrow">COLLECTION</p>
    <h2>当前合同集合</h2>
    <p>{qmdStatus?.collections.map((item) => `${item.name}${item.exists ? ` · ${item.document_count} 文档` : ' · 不可用'}`).join('，') || '正在读取 qmd 状态'}</p>
    <p>{runtimeStatus?.llm.has_api_key ? `LLM：${runtimeStatus.llm.model}` : 'LLM 未配置'}</p>
  </div>
  <Link className="ghost-button" to="/tasks">查看任务历史</Link>
</section>
```

- [ ] **Step 7: Add CSS**

Append to `frontend/src/styles/contract-agent.css`:

```css
.history-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 0;
}

.history-toolbar form {
  display: flex;
  gap: 8px;
  flex: 1;
}

.history-toolbar input,
.history-toolbar select {
  min-height: 40px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0 10px;
  background: #fff;
}

.history-toolbar input {
  flex: 1;
}

.history-list {
  display: grid;
  gap: 12px;
}

.history-row {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(180px, 0.7fr) auto;
  gap: 16px;
  align-items: center;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.history-row h2 {
  margin: 8px 0 4px;
  font-size: 18px;
}

.history-row p {
  margin: 0;
  color: #475569;
}

.history-metrics,
.history-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

- [ ] **Step 8: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run tests/TaskHistoryPage.test.tsx tests/UploadPage.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/UploadPage.tsx frontend/src/pages/TaskHistoryPage.tsx frontend/src/styles/contract-agent.css frontend/tests/TaskHistoryPage.test.tsx frontend/tests/UploadPage.test.tsx
git commit -m "feat: add task history workbench"
```

---

### Task 9: Frontend Task Detail Review, Dynamic Progress, And Exports

**Files:**
- Modify: `frontend/src/pages/TaskProgressPage.tsx`
- Modify: `frontend/src/styles/contract-agent.css`
- Create: `frontend/src/lib/reviewer.ts`
- Test: `frontend/tests/TaskProgressPage.test.tsx`

- [ ] **Step 1: Add reviewer storage helper test**

Create `frontend/tests/reviewer.test.ts`:

```typescript
import { afterEach, describe, expect, it } from 'vitest';
import { getReviewerName, setReviewerName } from '../src/lib/reviewer';

describe('reviewer storage', () => {
  afterEach(() => localStorage.clear());

  it('stores reviewer name trimmed', () => {
    setReviewerName(' 张三 ');
    expect(getReviewerName()).toBe('张三');
  });
});
```

- [ ] **Step 2: Update task detail test**

In `frontend/tests/TaskProgressPage.test.tsx`, extend the mocked result item to include:

```typescript
result_id: 'result-1',
review_status: 'unreviewed',
review_decision: null,
review_note: null,
reviewer_name: null,
reviewed_at: null,
```

Add assertions:

```typescript
expect(await screen.findByText('理解筛选条件')).toBeInTheDocument();
expect(screen.getByText('实时活动')).toBeInTheDocument();
expect(screen.getByRole('button', { name: '保存复核' })).toBeInTheDocument();
expect(screen.getByRole('link', { name: '导出 CSV' })).toHaveAttribute('href', '/api/screening-tasks/task-1/export.csv');
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run tests/reviewer.test.ts tests/TaskProgressPage.test.tsx
```

Expected: FAIL because helper and UI elements do not exist.

- [ ] **Step 4: Add reviewer helper**

Create `frontend/src/lib/reviewer.ts`:

```typescript
const REVIEWER_KEY = 'contract-agent-reviewer-name';

export function getReviewerName(): string {
  return localStorage.getItem(REVIEWER_KEY) || '';
}

export function setReviewerName(name: string): void {
  const trimmed = name.trim();
  if (trimmed) localStorage.setItem(REVIEWER_KEY, trimmed);
}
```

- [ ] **Step 5: Update task detail imports and state**

Modify `frontend/src/pages/TaskProgressPage.tsx` imports:

```tsx
import { copyScreeningTask, exportTaskUrl, getTaskResults, getTaskSummary, reviewDocumentResult } from '../lib/api';
import { buildTaskActivity } from '../lib/taskActivity';
import { getReviewerName, setReviewerName } from '../lib/reviewer';
import type { DocumentResultItem, ResultDecision, StreamEvent, TaskResults, TaskSummary } from '../lib/types';
```

Add state:

```tsx
const [decisionFilter, setDecisionFilter] = useState<'all' | ResultDecision>('all');
const [reviewFilter, setReviewFilter] = useState<'all' | 'reviewed' | 'unreviewed'>('all');
const [keyword, setKeyword] = useState('');
```

Add:

```tsx
const activity = useMemo(() => buildTaskActivity(summary, events), [summary, events]);
const filteredDocuments = useMemo(() => {
  return documents.filter((document) => {
    const decisionMatch = decisionFilter === 'all' || document.decision === decisionFilter;
    const reviewMatch = reviewFilter === 'all' || document.review_status === reviewFilter;
    const keywordText = `${document.document_title || ''} ${document.document_path} ${document.reason}`.toLowerCase();
    const keywordMatch = !keyword.trim() || keywordText.includes(keyword.trim().toLowerCase());
    return decisionMatch && reviewMatch && keywordMatch;
  });
}, [documents, decisionFilter, reviewFilter, keyword]);
```

- [ ] **Step 6: Replace static status strip mapping**

Render stages from `activity.stages`:

```tsx
<section className="agent-status-strip" aria-label="Agent 状态">
  {activity.stages.map((step, index) => (
    <div className={`agent-status-step ${step.state}`} key={step.key}>
      <span>{index + 1}</span>
      <strong>{step.label}</strong>
    </div>
  ))}
</section>
```

- [ ] **Step 7: Add activity stream panel**

Replace the current event list card with:

```tsx
<section className="side-card">
  <div className="card-heading">
    <h2>实时活动</h2>
  </div>
  <div className="activity-list">
    {activity.items.length ? activity.items.map((item) => (
      <span key={item.id}>{item.text}</span>
    )) : <span>等待后端事件...</span>}
  </div>
</section>
```

- [ ] **Step 8: Add filters and exports**

In the topbar actions:

```tsx
<div className="topbar-actions">
  <Link className="ghost-button" to="/tasks">任务历史</Link>
  {summary?.status === 'completed' ? (
    <>
      <a className="ghost-button" href={exportTaskUrl(taskId, 'csv')}>导出 CSV</a>
      <a className="ghost-button" href={exportTaskUrl(taskId, 'xlsx')}>导出 XLSX</a>
      <a className="ghost-button" href={exportTaskUrl(taskId, 'json')}>导出 JSON</a>
    </>
  ) : null}
  <Link className="ghost-button" to="/">新建筛选</Link>
</div>
```

Add result filters above `.result-list`:

```tsx
<div className="result-filters">
  <select aria-label="Agent 判断" value={decisionFilter} onChange={(event) => setDecisionFilter(event.currentTarget.value as 'all' | ResultDecision)}>
    <option value="all">全部判断</option>
    <option value="included">入选</option>
    <option value="uncertain">需确认</option>
    <option value="excluded">不符合</option>
  </select>
  <select aria-label="复核状态" value={reviewFilter} onChange={(event) => setReviewFilter(event.currentTarget.value as 'all' | 'reviewed' | 'unreviewed')}>
    <option value="all">全部复核状态</option>
    <option value="unreviewed">未复核</option>
    <option value="reviewed">已复核</option>
  </select>
  <input aria-label="筛选文档" value={keyword} onChange={(event) => setKeyword(event.currentTarget.value)} placeholder="按文档名或原因筛选" />
</div>
```

Use `filteredDocuments` for rendering.

- [ ] **Step 9: Add review panel**

Update `EvidencePanel` signature:

```tsx
function EvidencePanel({ document, taskId, onReviewed }: { document: DocumentResultItem | null; taskId: string; onReviewed: (item: DocumentResultItem) => void })
```

Inside non-empty panel, add state and form:

```tsx
const [reviewer, setReviewer] = useState(getReviewerName());
const [reviewDecision, setReviewDecision] = useState<ResultDecision>(document.review_decision || document.decision);
const [reviewNote, setReviewNote] = useState(document.review_note || '');
const [saving, setSaving] = useState(false);
const [saveError, setSaveError] = useState<string | null>(null);

useEffect(() => {
  setReviewDecision(document.review_decision || document.decision);
  setReviewNote(document.review_note || '');
}, [document.document_uri]);

async function saveReview() {
  if (!reviewer.trim()) {
    setSaveError('请填写复核人姓名');
    return;
  }
  setSaving(true);
  setSaveError(null);
  try {
    setReviewerName(reviewer);
    const response = await reviewDocumentResult(taskId, document.result_id, {
      review_status: 'reviewed',
      review_decision: reviewDecision,
      review_note: reviewNote,
      reviewer_name: reviewer
    });
    onReviewed(response.result);
  } catch (err) {
    setSaveError(err instanceof Error ? err.message : '保存复核失败');
  } finally {
    setSaving(false);
  }
}
```

Add JSX after judgment block:

```tsx
<section className="detail-block review-block">
  <h3>人工复核</h3>
  <label>
    复核人
    <input value={reviewer} onChange={(event) => setReviewer(event.currentTarget.value)} />
  </label>
  <label>
    人工判断
    <select value={reviewDecision} onChange={(event) => setReviewDecision(event.currentTarget.value as ResultDecision)}>
      <option value="included">入选</option>
      <option value="uncertain">需确认</option>
      <option value="excluded">不符合</option>
    </select>
  </label>
  <label>
    备注
    <textarea value={reviewNote} onChange={(event) => setReviewNote(event.currentTarget.value)} />
  </label>
  {document.review_status === 'reviewed' ? <p>已复核：{document.reviewer_name} {document.reviewed_at ? new Date(document.reviewed_at).toLocaleString() : ''}</p> : null}
  {saveError ? <p className="error-text">{saveError}</p> : null}
  <button className="primary-button full-width" type="button" disabled={saving} onClick={() => void saveReview()}>
    保存复核
  </button>
</section>
```

In parent:

```tsx
function updateReviewedResult(item: DocumentResultItem) {
  setResults((current) => {
    if (!current) return current;
    const buckets = { included: [...current.buckets.included], uncertain: [...current.buckets.uncertain], excluded: [...current.buckets.excluded] };
    (Object.keys(buckets) as ResultDecision[]).forEach((decision) => {
      buckets[decision] = buckets[decision].map((document) => document.result_id === item.result_id ? item : document);
    });
    return { ...current, buckets };
  });
}
```

Render:

```tsx
<EvidencePanel document={selectedDocument} taskId={taskId} onReviewed={updateReviewedResult} />
```

- [ ] **Step 10: Add CSS**

Append:

```css
.activity-list,
.result-filters,
.review-block {
  display: grid;
  gap: 10px;
}

.activity-list span {
  border-left: 3px solid #2563eb;
  padding-left: 10px;
  color: #334155;
}

.result-filters {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 12px;
}

.result-filters input,
.result-filters select,
.review-block input,
.review-block select,
.review-block textarea {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px 10px;
  background: #fff;
}

.review-block textarea {
  min-height: 88px;
  resize: vertical;
}

.topbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
```

- [ ] **Step 11: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run tests/reviewer.test.ts tests/taskActivity.test.ts tests/TaskProgressPage.test.tsx
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/lib/reviewer.ts frontend/src/pages/TaskProgressPage.tsx frontend/src/styles/contract-agent.css frontend/tests/reviewer.test.ts frontend/tests/TaskProgressPage.test.tsx
git commit -m "feat: add reviewable task detail"
```

---

### Task 10: Frontend Error Messaging And Acceptance Polish

**Files:**
- Create: `frontend/src/lib/errorMessages.ts`
- Modify: `frontend/src/pages/TaskProgressPage.tsx`
- Modify: `frontend/src/pages/UploadPage.tsx`
- Test: `frontend/tests/errorMessages.test.ts`
- Test: `frontend/tests/TaskProgressPage.test.tsx`

- [ ] **Step 1: Add failing error message tests**

Create `frontend/tests/errorMessages.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { failureMessage } from '../src/lib/errorMessages';

describe('failureMessage', () => {
  it('maps qmd and llm errors to actionable text', () => {
    expect(failureMessage('qmd_unavailable', 'Unable to reach qmd')).toContain('qmd MCP 不可访问');
    expect(failureMessage('agent_llm_not_configured', 'AGENT_LLM_API_KEY is required')).toContain('LLM 配置不可用');
    expect(failureMessage('worker_unexpected_error', 'Unexpected worker error')).toContain('worker 执行异常');
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd frontend
npm test -- --run tests/errorMessages.test.ts
```

Expected: FAIL because helper does not exist.

- [ ] **Step 3: Implement error message helper**

Create `frontend/src/lib/errorMessages.ts`:

```typescript
const messages: Record<string, string> = {
  agent_llm_not_configured: 'LLM 配置不可用。请检查 AGENT_LLM_API_KEY、AGENT_LLM_BASE_URL 和 AGENT_LLM_MODEL，然后重启 API/worker。',
  qmd_unavailable: 'qmd MCP 不可访问。请确认 qmd mcp --http --daemon 已启动，且 QMD_MCP_URL 可被 API/worker 访问。',
  qmd_collection_missing: '当前 qmd 集合不存在或没有文档。请检查 QMD_COLLECTIONS 与 qmd status。',
  worker_unexpected_error: 'worker 执行异常。请检查 worker 终端日志；macOS 本地运行建议使用 SimpleWorker 模式。',
  enqueue_failed: '任务无法入队。请检查 Redis/RQ 是否运行。'
};

export function failureMessage(code: string | null | undefined, fallback: string | null | undefined): string {
  if (code && messages[code]) return messages[code];
  return fallback || '任务执行失败，请检查 API 和 worker 日志。';
}
```

- [ ] **Step 4: Use helper in task detail**

Modify `TaskProgressPage.tsx`:

```tsx
import { failureMessage } from '../lib/errorMessages';
```

Replace failed error display:

```tsx
{error || summary?.status === 'failed' ? (
  <p className="error-text">{error || failureMessage(summary?.error_code, summary?.error_message)}</p>
) : null}
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run tests/errorMessages.test.ts tests/TaskProgressPage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/errorMessages.ts frontend/src/pages/TaskProgressPage.tsx frontend/tests/errorMessages.test.ts frontend/tests/TaskProgressPage.test.tsx
git commit -m "feat: add actionable failure messages"
```

---

### Task 11: Documentation And Phase 2 Acceptance Checklist

**Files:**
- Modify: `README.md`
- Create: `notes/phase-2-acceptance-checklist.md`

- [ ] **Step 1: Update README Phase 2 notes**

Add a `Phase 2 工作台能力` section after Phase 1.1:

```markdown
## Phase 2 工作台能力

Phase 2 将单次筛选链路升级为工作台：任务历史、动态进度、结果级人工复核、业务导出、qmd/运行健康摘要和本地 worker 稳定性加固。

人工复核仍然是单租户内网模型，不引入登录。前端要求输入复核人姓名并保存在浏览器本地，后端把该姓名作为业务留痕字段写入结果和导出。

本地 macOS 调试 worker 默认使用无 fork 的 `SimpleWorker`，避免 RQ fork 触发 Objective-C runtime 崩溃。可以通过 `RQ_WORKER_MODE=fork` 强制使用 RQ 默认 fork worker。
```

- [ ] **Step 2: Create acceptance checklist**

Create `notes/phase-2-acceptance-checklist.md`:

```markdown
# Phase 2 验收清单

验收日期：2026-06-23

## 范围

验收 Phase 2 工作台闭环：任务历史、复制任务、动态进度、结果级复核、CSV/XLSX/JSON 导出、qmd/运行健康摘要、失败提示和本地 worker 稳定性。

## 验收项

- [ ] 任务历史列表显示最近任务、状态、创建/完成时间、结果计数和复核计数。
- [ ] 任务历史支持状态筛选、关键词搜索和时间排序。
- [ ] 任意历史任务可复制为新任务，旧任务结果和复核记录不变。
- [ ] 任务详情显示六阶段进度：提交任务、理解筛选条件、检查合同集合、检索证据、分析文档、生成结果。
- [ ] 实时活动流显示条件解析、qmd 查询、候选数量和文档分类事件。
- [ ] 结果列表支持 Agent 判断、复核状态和关键词筛选。
- [ ] 用户可输入复核人姓名并保存复核结果。
- [ ] 复核结果保留 Agent 原始判断并新增人工判断、备注、复核人和复核时间。
- [ ] CSV/XLSX 导出包含业务汇总字段和证据摘要。
- [ ] JSON 导出包含任务、plan、结果、证据、复核字段和事件。
- [ ] 首页显示当前 qmd 集合和运行健康摘要。
- [ ] qmd 不可用、LLM 未配置、worker 异常和入队失败显示可操作错误文案。
- [ ] macOS 本地 worker 不再因 RQ fork 触发 ObjC 崩溃。

## 验证命令

```sh
cd backend
../.venv/bin/pytest

cd ../frontend
npm test -- --run
npm run build
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md notes/phase-2-acceptance-checklist.md
git commit -m "docs: add phase 2 acceptance notes"
```

---

### Task 12: Full Verification And Final Integration

**Files:**
- Read-only verification across the repository.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
../.venv/bin/pytest
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: all frontend tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0 and Vite reports built assets.

- [ ] **Step 4: Inspect staged and unstaged changes**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only intended changes remain, or working tree is clean if every task committed.

- [ ] **Step 5: Manual smoke test**

Start dependencies and app:

```bash
qmd mcp --http --daemon
docker compose up postgres redis
cd backend
../.venv/bin/alembic upgrade head
CONTRACT_AGENT_HOST=127.0.0.1 CONTRACT_AGENT_PORT=8000 ../.venv/bin/python -m app.main
```

In another terminal:

```bash
PYTHONPATH=backend .venv/bin/python -m app.worker
```

In another terminal:

```bash
cd frontend
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

Expected:

- `/` displays qmd and runtime health summary.
- `/tasks` displays history.
- Creating a task navigates to detail page.
- Activity stream updates during LLM/qmd/classification.
- Completed result can be reviewed.
- CSV, XLSX, and JSON export URLs return files.

- [ ] **Step 6: Commit any final documentation-only adjustments**

If manual smoke test requires README or checklist wording corrections:

```bash
git add README.md notes/phase-2-acceptance-checklist.md
git commit -m "docs: refine phase 2 workbench notes"
```

If no changes are needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Task history, filters, sorting, and copy are covered by Task 2 and Task 8.
- Result-level review, reviewer name, review status, review decision, notes, and audit are covered by Task 1, Task 3, and Task 9.
- CSV/XLSX/JSON exports are covered by Task 4 and Task 9.
- qmd and runtime health summaries are covered by Task 5 and Task 8.
- Dynamic progress and activity stream are covered by Task 7 and Task 9.
- Actionable failure messages are covered by Task 10.
- macOS worker stability is covered by Task 5.
- Documentation and acceptance checklist are covered by Task 11.
- Full regression and manual verification are covered by Task 12.

Placeholder scan:

- This plan contains no unfinished requirement markers or unspecified implementation placeholders.
- Each task names concrete files, commands, expected outcomes, and commit messages.

Type consistency:

- Backend review fields use `review_status`, `review_decision`, `review_note`, `reviewer_name`, and `reviewed_at` consistently across models, schemas, APIs, frontend types, and exports.
- Frontend `result_id` is introduced in `DocumentResultItem` and used for review routes.
- API paths match the Phase 2 spec: task list, copy, review, CSV/XLSX/JSON exports, qmd status, and runtime status.
