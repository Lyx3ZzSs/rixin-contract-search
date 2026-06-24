from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.enums import ResultDecision, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask, StreamEvent
from app.schemas import ScreeningCondition, ScreeningPlanPayload


class RecordingQmdClient:
    def __init__(self):
        self.queries = []

    def status(self):
        return {"collections": [{"name": "company_docs"}]}

    def query(self, query_text: str, collections: list[str], limit: int):
        self.queries.append(query_text)
        if query_text == "合同总价 人民币100万元":
            return [
                {
                    "docid": "#abc123",
                    "file": "company_docs/contracts/a.md",
                    "title": "A采购合同",
                    "score": 0.91,
                    "snippet": "合同总价为人民币100万元。",
                    "page_number": 3,
                }
            ]
        return []


class ScriptedAgentLlm:
    def plan(self, raw_query: str) -> ScreeningPlanPayload:
        return ScreeningPlanPayload(
            target="qmd_document",
            conditions=[
                ScreeningCondition(
                    id="amount",
                    description="合同总价包含人民币100万元",
                    operator="semantic_match",
                    value="人民币100万元",
                    qmd_queries=["金额条件初查"],
                    evidence_required=1,
                    structured=False,
                )
            ],
            decision_policy="phase1_keyword_candidate_uncertain_on_structured_comparison",
        )

    def refine_queries(self, raw_query: str, plan: ScreeningPlanPayload, missing_condition_ids: list[str]) -> dict[str, list[str]]:
        return {"amount": ["合同总价 人民币100万元"]}

    def classify_document(self, plan: ScreeningPlanPayload, document: dict) -> dict:
        return {
            "decision": "included",
            "reason": "agent_evidence_matched",
            "matched_conditions": ["amount"],
            "missing_conditions": [],
            "evidence": document["conditions"]["amount"],
            "confidence": 0.82,
        }


def test_langgraph_agent_refines_queries_and_persists_document_result(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="金额筛选",
        raw_query="筛选合同总价包含人民币100万元的合同",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    session.add(task)
    session.commit()
    qmd = RecordingQmdClient()

    result = ContractScreeningAgent(
        llm=ScriptedAgentLlm(),
        qmd=qmd,
        collections=["company_docs"],
        top_k=5,
        max_retrieval_rounds=2,
    ).run(session, task)

    assert qmd.queries == ["金额条件初查", "合同总价 人民币100万元"]
    assert result.qmd_result_count == 1
    assert result.document_count == 1

    plan = session.scalars(select(ScreeningPlan).where(ScreeningPlan.task_id == task.id)).one()
    assert plan.plan_json["conditions"][0]["qmd_queries"] == ["金额条件初查", "合同总价 人民币100万元"]

    document = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert document.decision == ResultDecision.included.value
    assert document.reason == "agent_evidence_matched"
    assert document.evidence[0]["page"] == 3

    events = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence)).all()
    assert "agent_refining_queries" in [event.event_type for event in events]


def test_langgraph_agent_commits_progress_events_before_slow_qmd_query(tmp_path):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    db_path = tmp_path / "progress-events.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    observed_event_types = []

    with TestingSession() as session:
        task = ScreeningTask(
            id=uuid4(),
            owner_id="internal-user",
            title="金额筛选",
            raw_query="筛选合同总价包含人民币100万元的合同",
            status=TaskStatus.retrieving.value,
            current_stage=TaskStatus.retrieving.value,
            progress_percent=10,
            metrics={},
        )
        session.add(task)
        session.commit()

        class ObservingQmdClient(RecordingQmdClient):
            def query(self, query_text: str, collections: list[str], limit: int):
                with TestingSession() as observer:
                    events = observer.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence)).all()
                    observed_event_types.append([event.event_type for event in events])
                return super().query(query_text, collections, limit)

        ContractScreeningAgent(
            llm=ScriptedAgentLlm(),
            qmd=ObservingQmdClient(),
            collections=["company_docs"],
            top_k=5,
            max_retrieval_rounds=2,
        ).run(session, task)

    assert any("qmd_searching" in event_types for event_types in observed_event_types)


class InvalidPlanLlm(ScriptedAgentLlm):
    def plan(self, raw_query: str):
        raise ValueError("invalid plan json")


def test_langgraph_agent_invalid_plan_raises_agent_error(db_session):
    from app.services.agent.langgraph_agent import AgentExecutionError, ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="无效计划",
        raw_query="INVALID_PLAN",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    session.add(task)
    session.commit()

    try:
        ContractScreeningAgent(
            llm=InvalidPlanLlm(),
            qmd=RecordingQmdClient(),
            collections=["company_docs"],
            top_k=5,
            max_retrieval_rounds=1,
        ).run(session, task)
    except AgentExecutionError as exc:
        assert exc.code == "agent_plan_invalid"
        assert "invalid plan json" in str(exc)
    else:
        raise AssertionError("expected AgentExecutionError")
