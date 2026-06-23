from uuid import uuid4

from sqlalchemy import select

from app.enums import ResultDecision, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningTask, StreamEvent
from app.schemas import ScreeningCondition, ScreeningPlanPayload


class FakeQmdClient:
    def status(self):
        return {"collections": [{"name": "company_docs", "files": 2}]}

    def query(self, query_text: str, collections: list[str], limit: int):
        assert collections == ["company_docs"]
        assert limit == 7
        return [
            {
                "docid": "#abc123",
                "file": "company_docs/contracts/a.md",
                "title": "A采购合同",
                "score": 0.91,
                "snippet": "合同总价为人民币100万元。",
                "line": 12,
            }
        ]


class EmptyQmdClient:
    def status(self):
        return {"collections": [{"name": "company_docs", "files": 0}]}

    def query(self, query_text: str, collections: list[str], limit: int):
        return []


class FlowTestAgentLlm:
    def plan(self, raw_query: str) -> ScreeningPlanPayload:
        return ScreeningPlanPayload(
            target="qmd_document",
            conditions=[
                ScreeningCondition(
                    id="general_match",
                    description=raw_query,
                    operator="semantic_match",
                    value=raw_query,
                    qmd_queries=[raw_query],
                    evidence_required=1,
                    structured=False,
                )
            ],
            decision_policy="phase1_keyword_candidate_uncertain_on_structured_comparison",
        )

    def refine_queries(self, raw_query: str, plan: ScreeningPlanPayload, missing_condition_ids: list[str]) -> dict[str, list[str]]:
        return {}

    def classify_document(self, plan: ScreeningPlanPayload, document: dict) -> dict:
        return {
            "decision": "included",
            "reason": "test_llm_evidence_matched",
            "matched_conditions": ["general_match"],
            "missing_conditions": [],
            "evidence": document["conditions"]["general_match"],
            "confidence": 0.8,
        }


def test_create_screening_task_uses_json_without_uploads(client, db_session, monkeypatch):
    import app.api.screening_tasks as routes

    monkeypatch.setattr(routes, "enqueue_screening_task", lambda task_id: f"job-{task_id}")

    response = client.post("/api/screening-tasks", json={"query": "筛选合同总价包含人民币100万元的合同"})

    assert response.status_code == 200
    body = response.json()
    assert body["raw_query"] == "筛选合同总价包含人民币100万元的合同"
    assert body["events_url"].endswith("/events")
    assert body["results_url"].endswith("/results")

    session, _ = db_session
    task = session.get(ScreeningTask, body["task_id"])
    assert task is not None
    assert task.metrics["rq_job_id"] == f"job-{task.id}"


def test_screening_task_rejects_multipart_uploads(client):
    response = client.post(
        "/api/screening-tasks",
        data={"query": "合同总价"},
        files={"files": ("contract.pdf", b"%PDF-1.4\n", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "json_required"


def test_contract_import_route_is_not_registered(client):
    response = client.post("/api/contracts/imports")

    assert response.status_code == 404


def test_worker_queries_qmd_mcp_and_persists_document_results(client, db_session, monkeypatch):
    import app.application.screening_runner as runner

    session, TestingSession = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="合同总价",
        raw_query="合同总价 人民币100万元",
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={},
    )
    session.add(task)
    session.commit()

    monkeypatch.setattr(runner, "SessionLocal", TestingSession)
    monkeypatch.setattr(runner, "QmdClient", lambda: FakeQmdClient())
    monkeypatch.setattr(runner, "create_agent_llm", lambda: FlowTestAgentLlm())
    monkeypatch.setattr(runner.settings, "QMD_COLLECTIONS", "company_docs")
    monkeypatch.setattr(runner.settings, "QMD_TOP_K", 7)

    runner.run_screening_task(str(task.id))

    session.expire_all()
    completed = session.get(ScreeningTask, task.id)
    assert completed.status == TaskStatus.completed.value
    assert completed.progress_percent == 100

    result = session.scalars(select(ScreeningDocumentResult)).one()
    assert result.task_id == task.id
    assert result.collection == "company_docs"
    assert result.document_uri == "qmd://company_docs/contracts/a.md"
    assert result.document_path == "contracts/a.md"
    assert result.document_title == "A采购合同"
    assert result.decision == ResultDecision.included.value
    assert result.evidence[0]["text"] == "合同总价为人民币100万元。"

    response = client.get(f"/api/screening-tasks/{task.id}/results")
    assert response.status_code == 200
    item = response.json()["buckets"]["included"][0]
    assert item["document_uri"] == "qmd://company_docs/contracts/a.md"
    assert item["document_path"] == "contracts/a.md"
    assert item["collection"] == "company_docs"
    assert item["evidence"][0]["artifact_ref"] == "qmd://company_docs/contracts/a.md"


def test_worker_completes_with_empty_results(client, db_session, monkeypatch):
    import app.application.screening_runner as runner

    session, TestingSession = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="无命中",
        raw_query="NO_MATCH",
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={},
    )
    session.add(task)
    session.commit()

    monkeypatch.setattr(runner, "SessionLocal", TestingSession)
    monkeypatch.setattr(runner, "QmdClient", lambda: EmptyQmdClient())
    monkeypatch.setattr(runner, "create_agent_llm", lambda: FlowTestAgentLlm())
    monkeypatch.setattr(runner.settings, "QMD_COLLECTIONS", "company_docs")

    runner.run_screening_task(str(task.id))

    session.expire_all()
    completed = session.get(ScreeningTask, task.id)
    assert completed.status == TaskStatus.completed.value
    assert completed.metrics["qmd_result_count"] == 0
    assert session.scalars(select(ScreeningDocumentResult)).all() == []

    events = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence)).all()
    assert [event.event_type for event in events][-1] == "task_completed"


def test_worker_unexpected_error_records_exception_details(client, db_session, monkeypatch):
    import app.application.screening_runner as runner

    session, TestingSession = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="异常诊断",
        raw_query="触发未知异常",
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={},
    )
    session.add(task)
    session.commit()

    def raise_unexpected(task_id):
        raise ValueError("diagnostic boom")

    monkeypatch.setattr(runner, "SessionLocal", TestingSession)
    monkeypatch.setattr(runner, "retrieve_and_classify", raise_unexpected)

    runner.run_screening_task(str(task.id))

    session.expire_all()
    failed = session.get(ScreeningTask, task.id)
    assert failed.status == TaskStatus.failed.value
    assert failed.error_code == "worker_unexpected_error"
    assert failed.error_message == "Unexpected worker error"

    event = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence.desc())).first()
    assert event.event_type == "task_failed"
    assert event.payload["exception_type"] == "ValueError"
    assert event.payload["exception_message"] == "diagnostic boom"


def test_worker_fails_with_diagnostic_when_llm_is_not_configured(client, db_session, monkeypatch):
    import app.application.screening_runner as runner
    from app.services.agent.llm import AgentLlmConfigurationError

    session, TestingSession = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="缺少 LLM",
        raw_query="合同总价",
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={},
    )
    session.add(task)
    session.commit()

    monkeypatch.setattr(runner, "SessionLocal", TestingSession)
    monkeypatch.setattr(runner, "create_agent_llm", lambda: (_ for _ in ()).throw(AgentLlmConfigurationError("AGENT_LLM_API_KEY is required")))

    runner.run_screening_task(str(task.id))

    session.expire_all()
    failed = session.get(ScreeningTask, task.id)
    assert failed.status == TaskStatus.failed.value
    assert failed.error_code == "agent_llm_not_configured"
    assert failed.error_message == "AGENT_LLM_API_KEY is required"

    event = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence.desc())).first()
    assert event.event_type == "task_failed"
    assert event.payload["stage"] == "planning"
