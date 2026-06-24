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
