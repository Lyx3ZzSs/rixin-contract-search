from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect

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
