from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.enums import ConditionVerdictValue, EvidenceRole, ResultDecision, VerificationStatus
from app.schemas import AgentEvalMetrics, DocumentResultItem, ScreeningCondition, ScreeningPlanPayload


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


def test_screening_condition_syncs_v2_required_evidence_count_to_legacy_field():
    plan = ScreeningPlanPayload.model_validate(
        {
            "target": "qmd_document",
            "plan_version": 2,
            "conditions": [
                {
                    "id": "multi_evidence_amount",
                    "description": "合同总价大于等于100万元",
                    "condition_type": "amount",
                    "operator": "gte",
                    "value": 1000000,
                    "qmd_queries": ["合同总价 人民币 金额"],
                    "required_evidence_count": 3,
                    "structured": True,
                }
            ],
            "decision_policy": "all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
        }
    )

    condition = plan.conditions[0]
    assert condition.required_evidence_count == 3
    assert condition.evidence_required == 3


def test_screening_condition_preserves_v1_evidence_required():
    condition = ScreeningCondition(
        id="general_match",
        description="包含验收付款条款",
        operator="semantic_match",
        value="验收付款条款",
        qmd_queries=["验收付款"],
        evidence_required=2,
        structured=False,
    )

    assert condition.evidence_required == 2
    assert condition.required_evidence_count == 2


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("evidence_required", 0),
        ("evidence_required", -1),
        ("required_evidence_count", 0),
        ("required_evidence_count", -1),
    ],
)
def test_screening_condition_rejects_non_positive_evidence_counts(field_name, value):
    payload = {
        "id": "general_match",
        "description": "包含验收付款条款",
        "operator": "semantic_match",
        "value": "验收付款条款",
        "qmd_queries": ["验收付款"],
        "structured": False,
        field_name: value,
    }

    with pytest.raises(ValidationError):
        ScreeningCondition.model_validate(payload)


def test_screening_plan_rejects_unsupported_plan_version():
    with pytest.raises(ValidationError):
        ScreeningPlanPayload.model_validate(
            {
                "target": "qmd_document",
                "plan_version": 3,
                "conditions": [
                    {
                        "id": "general_match",
                        "description": "包含验收付款条款",
                        "operator": "semantic_match",
                        "value": "验收付款条款",
                        "qmd_queries": ["验收付款"],
                        "structured": False,
                    }
                ],
                "decision_policy": "phase1_keyword_candidate_uncertain_on_structured_comparison",
            }
        )


@pytest.mark.parametrize("plan_version", [True, 1.0])
def test_screening_plan_rejects_non_integer_plan_versions(plan_version):
    with pytest.raises(ValidationError):
        ScreeningPlanPayload.model_validate(
            {
                "target": "qmd_document",
                "plan_version": plan_version,
                "conditions": [
                    {
                        "id": "general_match",
                        "description": "包含验收付款条款",
                        "operator": "semantic_match",
                        "value": "验收付款条款",
                        "qmd_queries": ["验收付款"],
                        "structured": False,
                    }
                ],
                "decision_policy": "phase1_keyword_candidate_uncertain_on_structured_comparison",
            }
        )


def test_phase3_rate_fields_are_bounded():
    now = datetime.now()

    with pytest.raises(ValidationError):
        DocumentResultItem(
            result_id=uuid4(),
            document_uri="qmd://doc/1",
            document_path="/tmp/doc.md",
            collection="contracts",
            decision=ResultDecision.uncertain,
            reason="Missing verified evidence",
            matched_conditions=[],
            missing_conditions=["amount_threshold"],
            evidence=[],
            confidence=0.5,
            evidence_support_rate=1.1,
            created_at=now,
            updated_at=now,
        )

    with pytest.raises(ValidationError):
        AgentEvalMetrics(
            precision=0.9,
            recall=0.8,
            uncertain_rate=-0.1,
            evidence_support_rate=0.7,
            schema_failure_rate=0.0,
            verification_failure_rate=0.2,
        )


def test_phase3_enums_are_string_values():
    assert ConditionVerdictValue.satisfied.value == "satisfied"
    assert VerificationStatus.deep_read_verified.value == "deep_read_verified"
    assert EvidenceRole.supporting.value == "supporting"
