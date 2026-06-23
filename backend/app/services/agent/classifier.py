from uuid import UUID

from app.enums import ParseStatus, ResultDecision
from app.models import ContractFile
from app.schemas import ContractScreeningDecision, EvidenceItem, ScreeningPlanPayload


def classify_contract(contract: ContractFile, plan: ScreeningPlanPayload, snippets_by_condition: dict[str, list[EvidenceItem]]) -> ContractScreeningDecision:
    all_conditions = [condition.id for condition in plan.conditions]
    if contract.parse_status == ParseStatus.failed.value:
        return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.uncertain, reason="parse_failed", matched_conditions=[], missing_conditions=all_conditions, evidence=[], confidence=0.0)

    matched = []
    missing = []
    evidence: list[EvidenceItem] = []
    structured_matched = False
    for condition in plan.conditions:
        items = snippets_by_condition.get(condition.id, [])
        if len(items) >= condition.evidence_required:
            matched.append(condition.id)
            evidence.extend(items)
            structured_matched = structured_matched or condition.structured
        else:
            missing.append(condition.id)
    evidence = evidence[:10]

    if contract.parse_status == ParseStatus.low_quality.value:
        return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.uncertain, reason="low_quality_parse", matched_conditions=matched, missing_conditions=missing, evidence=evidence, confidence=0.2)
    if not matched:
        return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.uncertain, reason="no_evidence", matched_conditions=[], missing_conditions=all_conditions, evidence=[], confidence=0.1)
    if structured_matched:
        return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.uncertain, reason="structured_condition_requires_review", matched_conditions=matched, missing_conditions=missing, evidence=evidence, confidence=0.45)
    if not missing:
        return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.included, reason="keyword_evidence_matched", matched_conditions=matched, missing_conditions=[], evidence=evidence, confidence=0.65)
    return ContractScreeningDecision(contract_id=contract.id, decision=ResultDecision.uncertain, reason="no_evidence", matched_conditions=[], missing_conditions=all_conditions, evidence=[], confidence=0.1)


def classify_document(plan: ScreeningPlanPayload, snippets_by_condition: dict[str, list[EvidenceItem]]) -> dict:
    all_conditions = [condition.id for condition in plan.conditions]
    matched = []
    missing = []
    evidence: list[EvidenceItem] = []
    structured_matched = False
    for condition in plan.conditions:
        items = snippets_by_condition.get(condition.id, [])
        if len(items) >= condition.evidence_required:
            matched.append(condition.id)
            evidence.extend(items)
            structured_matched = structured_matched or condition.structured
        else:
            missing.append(condition.id)
    evidence = evidence[:10]
    if not matched:
        return {"decision": ResultDecision.uncertain, "reason": "no_evidence", "matched_conditions": [], "missing_conditions": all_conditions, "evidence": [], "confidence": 0.1}
    if structured_matched:
        return {"decision": ResultDecision.uncertain, "reason": "structured_condition_requires_review", "matched_conditions": matched, "missing_conditions": missing, "evidence": evidence, "confidence": 0.45}
    if not missing:
        return {"decision": ResultDecision.included, "reason": "keyword_evidence_matched", "matched_conditions": matched, "missing_conditions": [], "evidence": evidence, "confidence": 0.65}
    return {"decision": ResultDecision.uncertain, "reason": "partial_evidence", "matched_conditions": matched, "missing_conditions": missing, "evidence": evidence, "confidence": 0.35}
