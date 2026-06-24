from app.enums import ConditionVerdictValue, EvidenceRole, VerificationStatus
from app.schemas import ScreeningCondition, ScreeningPlanPayload


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


def test_phase3_enums_are_string_values():
    assert ConditionVerdictValue.satisfied.value == "satisfied"
    assert VerificationStatus.deep_read_verified.value == "deep_read_verified"
    assert EvidenceRole.supporting.value == "supporting"
