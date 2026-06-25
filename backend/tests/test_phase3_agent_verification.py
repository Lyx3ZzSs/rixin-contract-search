from uuid import uuid4

from sqlalchemy import select

from app.enums import ConditionVerdictValue, ResultDecision, TaskStatus, UncertainReason, VerificationStatus, VerificationStrategy
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


class AcquisitionTermQmd(DeepReadQmd):
    def __init__(self):
        self.grep_patterns = []

    def query(self, query_text: str, collections: list[str], limit: int):
        return [
            {
                "docid": "doc-1",
                "file": "qmd://company_docs/contracts/equipment.md",
                "title": "设备采购合同",
                "score": 0.93,
                "snippet": "# 设备采购合同 ## 一、合同基本信息",
            }
        ]

    def doc_grep(self, document_uri: str, pattern: str):
        self.grep_patterns.append(pattern)
        if pattern == "GPU服务器":
            return {"structuredContent": {"matches": [{"page": 20, "text": "| 1 | GPU服务器 | 4台 |", "anchor": "line:20"}]}}
        return {"structuredContent": {"matches": []}}

    def doc_read(self, document_uri: str, page=None, anchor=None, window=2):
        return {"structuredContent": {"text": "| 1 | GPU服务器 | 4台 |", "page": page, "anchor": anchor}}


class SemanticDocumentQueryQmd(DeepReadQmd):
    def __init__(self):
        self.grep_patterns = []
        self.semantic_questions = []

    def query(self, query_text: str, collections: list[str], limit: int):
        return [
            {
                "docid": "doc-1",
                "file": "qmd://company_docs/contracts/scanned.md",
                "title": "扫描设备合同",
                "score": 0.9,
                "snippet": "# 扫描设备合同",
            }
        ]

    def doc_grep(self, document_uri: str, pattern: str):
        self.grep_patterns.append(pattern)
        return {"structuredContent": {"matches": []}}

    def doc_query(self, document_uri: str, question: str):
        self.semantic_questions.append(question)
        return {"structuredContent": {"matches": [{"page": 20, "text": "OCR片段：G P U 服务器 4台", "anchor": "line:20"}]}}

    def doc_read(self, document_uri: str, page=None, anchor=None, window=2):
        return {"structuredContent": {"text": "OCR片段：G P U 服务器 4台，型号HD-GPU-4090-4U。", "page": page, "anchor": anchor}}


class TocGuidedReadQmd(DeepReadQmd):
    def __init__(self):
        self.read_anchors = []

    def query(self, query_text: str, collections: list[str], limit: int):
        return [
            {
                "docid": "doc-1",
                "file": "qmd://company_docs/contracts/equipment.md",
                "title": "设备采购合同",
                "score": 0.9,
                "snippet": "# 设备采购合同",
            }
        ]

    def doc_grep(self, document_uri: str, pattern: str):
        return {"structuredContent": {"matches": []}}

    def doc_query(self, document_uri: str, question: str):
        return {"structuredContent": {"matches": []}}

    def doc_toc(self, document_uri: str):
        return {
            "structuredContent": {
                "sections": [
                    {"title": "一、合同基本信息", "address": "line:1-10", "children": []},
                    {"title": "二、采购内容", "address": "line:11-30", "children": []},
                ]
            }
        }

    def doc_read(self, document_uri: str, page=None, anchor=None, window=2):
        self.read_anchors.append(anchor)
        return {"structuredContent": {"text": "采购内容：GPU服务器4台，存储服务器2台。", "page": page, "anchor": anchor}}


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


class AcquisitionTermLlm(VerdictLlm):
    def plan(self, raw_query: str):
        return ScreeningPlanPayload(
            target="qmd_document",
            plan_version=2,
            conditions=[
                ScreeningCondition(
                    id="gpu_server",
                    description="合同采购了GPU服务器",
                    operator="semantic_match",
                    value="采购GPU服务器",
                    qmd_queries=["采购GPU服务器", "购买GPU服务器", "GPU服务器采购"],
                    evidence_terms=["GPU服务器"],
                    semantic_questions=["合同是否采购GPU服务器？"],
                    target_sections=["采购内容"],
                    verification_strategy="grep_then_read",
                    required_evidence_count=1,
                    evidence_required=1,
                    structured=False,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )


class SemanticLocatorLlm(VerdictLlm):
    def plan(self, raw_query: str):
        return ScreeningPlanPayload(
            target="qmd_document",
            plan_version=2,
            conditions=[
                ScreeningCondition(
                    id="gpu_server",
                    description="合同采购了GPU服务器",
                    operator="semantic_match",
                    value="采购GPU服务器",
                    qmd_queries=["采购GPU服务器"],
                    evidence_terms=["GPU服务器"],
                    semantic_questions=["合同是否采购GPU服务器？"],
                    target_sections=["采购内容"],
                    verification_strategy="grep_then_read",
                    required_evidence_count=1,
                    evidence_required=1,
                    structured=False,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )


class ForgedEvidenceSatisfiedLlm(VerdictLlm):
    def judge_condition(self, plan, condition, document, evidence):
        forged = {
            "page": 999,
            "text": "伪造的证据",
            "context": "伪造的上下文",
            "source": "qmd",
            "score": 0.01,
            "condition_id": condition.id,
            "artifact_ref": "qmd://fake/contracts/forged.md",
            "document_uri": "qmd://fake/contracts/forged.md",
            "role": "supporting",
            "source_tool": "manual_upload",
            "document_path": "/tmp/forged.md",
            "collection": "fake_collection",
            "anchor": "fake-anchor",
            "used_for_decision": True,
        }
        return {
            "verdict": "satisfied",
            "confidence": 0.86,
            "supporting_evidence": [forged],
            "contradicting_evidence": [],
            "missing_reason": None,
        }


class ContradictingEvidenceVerdictLlm(VerdictLlm):
    def __init__(self, verdict: str):
        self.verdict = verdict

    def judge_condition(self, plan, condition, document, evidence):
        return {
            "verdict": self.verdict,
            "confidence": 0.41,
            "supporting_evidence": [],
            "contradicting_evidence": evidence,
            "missing_reason": None,
        }


class ForgedContradictingEvidenceLlm(VerdictLlm):
    def judge_condition(self, plan, condition, document, evidence):
        forged = {
            "page": 999,
            "text": "伪造的反证据",
            "context": "伪造的反证据上下文",
            "source": "qmd",
            "score": 0.01,
            "condition_id": condition.id,
            "artifact_ref": "qmd://fake/contracts/forged-contradiction.md",
            "document_uri": "qmd://fake/contracts/forged-contradiction.md",
            "role": "contradicting",
            "source_tool": "manual_upload",
            "document_path": "/tmp/forged-contradiction.md",
            "collection": "fake_collection",
            "anchor": "fake-anchor",
            "used_for_decision": True,
        }
        return {
            "verdict": "conflicting",
            "confidence": 0.41,
            "supporting_evidence": [],
            "contradicting_evidence": [forged],
            "missing_reason": None,
        }


class ConflictingWithoutEvidenceLlm(VerdictLlm):
    def judge_condition(self, plan, condition, document, evidence):
        return {
            "verdict": "conflicting",
            "confidence": 0.41,
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "missing_reason": None,
        }


class StrictCountVerdictLlm(VerdictLlm):
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
                    required_evidence_count=2,
                    evidence_required=2,
                    structured=True,
                )
            ],
            decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        )


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


def test_agent_grep_verification_falls_back_to_salient_condition_term(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="设备筛选",
        raw_query="哪份合同采购了GPU服务器？",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    qmd = AcquisitionTermQmd()
    session.add(task)
    session.commit()

    ContractScreeningAgent(llm=AcquisitionTermLlm(), qmd=qmd, collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    assert qmd.grep_patterns == ["GPU服务器"]
    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.included.value
    assert result.evidence_support_rate == 1.0


def test_agent_uses_document_semantic_query_when_grep_misses_ocr_text(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="扫描件筛选",
        raw_query="哪份合同采购了GPU服务器？",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    qmd = SemanticDocumentQueryQmd()
    session.add(task)
    session.commit()

    ContractScreeningAgent(llm=SemanticLocatorLlm(), qmd=qmd, collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    assert qmd.grep_patterns
    assert qmd.semantic_questions == ["合同是否采购GPU服务器？"]
    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.included.value
    assert result.evidence_support_rate == 1.0


def test_agent_reads_target_section_when_grep_and_semantic_query_miss(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    session, _ = db_session
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="章节筛选",
        raw_query="哪份合同采购了GPU服务器？",
        status=TaskStatus.retrieving.value,
        current_stage=TaskStatus.retrieving.value,
        progress_percent=10,
        metrics={},
    )
    qmd = TocGuidedReadQmd()
    session.add(task)
    session.commit()

    ContractScreeningAgent(llm=SemanticLocatorLlm(), qmd=qmd, collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    assert qmd.read_anchors == ["line:11-30"]
    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.included.value
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
    assert verdict.missing_reason == "verification_failed"

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.uncertain.value
    assert result.evidence == []
    assert result.verification_status == VerificationStatus.verification_failed.value
    assert UncertainReason.verification_failed.value in result.uncertain_reasons


def test_agent_ignores_forged_llm_evidence_and_keeps_gathered_provenance(db_session):
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

    ContractScreeningAgent(llm=ForgedEvidenceSatisfiedLlm(), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.satisfied.value
    assert verdict.supporting_evidence[0]["source_tool"] == "doc_read"
    assert verdict.supporting_evidence[0]["text"] == "第三页：合同总价为人民币120万元，含税。"
    assert verdict.supporting_evidence[0]["artifact_ref"] == "qmd://company_docs/contracts/a.md"
    assert verdict.supporting_evidence[0]["source_tool"] != "manual_upload"


def test_agent_preserves_matching_contradicting_evidence_and_rejects_forged_contradictions(db_session):
    from app.services.agent.langgraph_agent import ContractScreeningAgent

    for verdict_value, expected_decision, expected_reason, expected_uncertain_reason in [
        ("conflicting", ResultDecision.uncertain.value, "condition_missing_or_conflicting", UncertainReason.conflicting_evidence.value),
        ("not_satisfied", ResultDecision.excluded.value, "condition_not_satisfied", None),
    ]:
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

        ContractScreeningAgent(llm=ContradictingEvidenceVerdictLlm(verdict_value), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

        verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
        assert verdict.verdict == verdict_value
        assert verdict.contradicting_evidence
        assert verdict.contradicting_evidence[0]["source_tool"] == "doc_read"
        assert verdict.contradicting_evidence[0]["artifact_ref"] == "qmd://company_docs/contracts/a.md"

        result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
        assert result.decision == expected_decision
        assert result.reason == expected_reason
        if expected_uncertain_reason is None:
            assert result.uncertain_reasons == []
        else:
            assert expected_uncertain_reason in result.uncertain_reasons

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

    ContractScreeningAgent(llm=ForgedContradictingEvidenceLlm(), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.unknown.value
    assert verdict.contradicting_evidence == []

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.uncertain.value
    assert UncertainReason.missing_evidence.value in result.uncertain_reasons
    assert UncertainReason.conflicting_evidence.value not in result.uncertain_reasons


def test_agent_downgrades_conflicting_verdict_without_trusted_contradicting_evidence(db_session):
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

    ContractScreeningAgent(llm=ConflictingWithoutEvidenceLlm(), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.unknown.value
    assert verdict.confidence == 0.0
    assert verdict.contradicting_evidence == []
    assert verdict.missing_reason == "contradicting_evidence_required"

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision == ResultDecision.uncertain.value
    assert UncertainReason.missing_evidence.value in result.uncertain_reasons
    assert UncertainReason.conflicting_evidence.value not in result.uncertain_reasons


def test_agent_requires_minimum_supporting_evidence_count(db_session):
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

    ContractScreeningAgent(llm=StrictCountVerdictLlm(), qmd=DeepReadQmd(), collections=["company_docs"], top_k=5, max_retrieval_rounds=1).run(session, task)

    verdict = session.scalars(select(ConditionVerdict).where(ConditionVerdict.task_id == task.id)).one()
    assert verdict.verdict == ConditionVerdictValue.unknown.value
    assert verdict.supporting_evidence != []
    assert verdict.missing_reason == "insufficient_supporting_evidence"
    assert verdict.confidence == 0.0

    result = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).one()
    assert result.decision != ResultDecision.included.value
    assert result.decision == ResultDecision.uncertain.value
    assert result.evidence_support_rate == 0.0


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
