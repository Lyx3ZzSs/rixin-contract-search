from app.enums import VerificationStrategy
from app.schemas import ScreeningCondition, ScreeningPlanPayload


def build_screening_plan(query: str) -> ScreeningPlanPayload:
    structured = any(marker in query for marker in ["大于", "小于", "超过", "不少于", "不低于", "金额"])
    queries = [query]
    if "金额" in query or "合同总价" in query or "价" in query:
        queries.append("合同总价 人民币 万元")
    deduped = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    condition = ScreeningCondition(
        id="general_match",
        description=query,
        operator="semantic_match",
        value=query,
        qmd_queries=deduped,
        evidence_required=1,
        structured=structured,
        verification_strategy=VerificationStrategy.grep_then_read,
        evidence_terms=deduped,
        semantic_questions=[query],
        target_sections=[],
    )
    return ScreeningPlanPayload(
        target="qmd_document",
        plan_version=2,
        conditions=[condition],
        decision_policy="all_required_conditions_satisfied_else_uncertain_on_missing_or_conflict",
    )
