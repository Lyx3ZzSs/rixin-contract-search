from uuid import uuid4

from sqlalchemy import select

from app.enums import ConditionVerdictValue, ResultDecision, TaskStatus, VerificationStatus, VerificationStrategy
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


class EmptyDeepReadQmd(DeepReadQmd):
    def doc_grep(self, document_uri: str, pattern: str):
        return {"structuredContent": {"matches": []}}

    def doc_read(self, document_uri: str, page=None, anchor=None, window=2):
        return {"structuredContent": {"text": ""}}


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


class EmptyEvidenceSatisfiedLlm(VerdictLlm):
    def judge_condition(self, plan, condition, document, evidence):
        return {
            "verdict": "satisfied",
            "confidence": 0.86,
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "missing_reason": None,
        }


class QueryOnlyQmd:
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


class QueryOnlyVerdictLlm(VerdictLlm):
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
                    verification_strategy="query_only",
                    required_evidence_count=1,
                    evidence_required=1,
                    structured=True,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )


class UnsupportedStrategyVerdictLlm(VerdictLlm):
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
                    verification_strategy="doc_query",
                    required_evidence_count=1,
                    evidence_required=1,
                    structured=True,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )


class UnsupportedStrategyQmd(QueryOnlyQmd):
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


def test_agent_query_only_satisfied_condition_persists_query_only_status(db_session):
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

    ContractScreeningAgent(llm=QueryOnlyVerdictLlm(), qmd=QueryOnlyQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.satisfied.value
    assert verdict.supporting_evidence[0]["source_tool"] == "query"

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.included.value
    assert result.verification_status == VerificationStatus.query_only.value
    assert result.evidence_support_rate == 1.0


def test_agent_fails_closed_when_deep_read_evidence_is_missing(db_session):
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

    ContractScreeningAgent(llm=EmptyEvidenceSatisfiedLlm(), qmd=EmptyDeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.unknown.value
    assert verdict.supporting_evidence == []
    assert verdict.missing_reason == "supporting_evidence_required"

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.uncertain.value
    assert result.evidence == []
    assert result.verification_status != VerificationStatus.deep_read_verified.value


def test_agent_fails_closed_for_unsupported_verification_strategy(db_session):
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

    ContractScreeningAgent(llm=UnsupportedStrategyVerdictLlm(), qmd=UnsupportedStrategyQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.unknown.value
    assert verdict.supporting_evidence == []
    assert verdict.missing_reason == "unsupported_verification_strategy"
    assert verdict.verification_method == VerificationStrategy.doc_query.value

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.uncertain.value
    assert result.evidence == []
    assert result.verification_status != VerificationStatus.deep_read_verified.value
