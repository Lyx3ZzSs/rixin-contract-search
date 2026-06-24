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
