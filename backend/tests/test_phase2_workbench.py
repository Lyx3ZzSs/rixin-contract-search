from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect

from app.enums import ResultDecision, ReviewStatus, TaskStatus
from app.models import AuditEvent, ScreeningDocumentResult, ScreeningTask


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
    session, _ = db_session
    inspector = inspect(session.get_bind())
    columns = {column["name"] for column in inspector.get_columns("screening_document_results")}
    assert {"review_status", "review_decision", "review_note", "reviewer_name", "reviewed_at"} <= columns


def test_phase2_migration_adds_review_columns():
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0003_phase2_workbench.py"
    migration = migration_path.read_text(encoding="utf-8")
    assert "review_status" in migration
    assert "review_decision" in migration
    assert "review_note" in migration
    assert "reviewer_name" in migration
    assert "reviewed_at" in migration


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
