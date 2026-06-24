from typing import Any

from sqlalchemy.orm import Session

from app.enums import (
    ConditionVerdictValue,
    EvidenceRole,
    EvidenceSourceTool,
    ResultDecision,
    UncertainReason,
    VerificationStatus,
    VerificationStrategy,
)
from app.models import ConditionVerdict, ScreeningDocumentResult, ScreeningTask
from app.schemas import ScreeningCondition, ScreeningPlanPayload
from app.services.agent.aggregator import aggregate_document_candidates


def verify_documents(session: Session, task: ScreeningTask, plan: ScreeningPlanPayload, qmd: Any, llm: Any) -> int:
    documents = aggregate_document_candidates(session, task.id, plan)
    for document in documents.values():
        verdicts = []
        for condition in plan.conditions:
            evidence = _gather_evidence(qmd, document, condition)
            raw_verdict = _judge_condition(llm, plan, condition, document, evidence)
            verdict = _persist_condition_verdict(session, task, document, condition, raw_verdict)
            verdicts.append(verdict)
        session.add(_build_document_result(task, document, plan, verdicts))
    return len(documents)


def _gather_evidence(qmd: Any, document: dict[str, Any], condition: ScreeningCondition) -> list[dict[str, Any]]:
    strategy = _enum_value(condition.verification_strategy)
    if strategy == VerificationStrategy.grep_then_read.value:
        return _grep_then_read_evidence(qmd, document, condition)
    return _query_only_evidence(document, condition)


def _grep_then_read_evidence(qmd: Any, document: dict[str, Any], condition: ScreeningCondition) -> list[dict[str, Any]]:
    document_uri = str(document["document_uri"])
    query_text = condition.qmd_queries[0] if condition.qmd_queries else condition.description
    try:
        grep_payload = qmd.doc_grep(document_uri, query_text)
        first = _first_match(grep_payload)
        read_payload = qmd.doc_read(document_uri, page=first.get("page"), anchor=first.get("anchor"), window=2)
    except Exception:
        return []
    structured = read_payload.get("structuredContent") if isinstance(read_payload, dict) else None
    structured = structured if isinstance(structured, dict) else {}
    text = str(structured.get("text") or first.get("text") or "").strip()
    if not text:
        return []
    page = _coerce_int(structured.get("page", first.get("page")))
    anchor = structured.get("anchor", first.get("anchor"))
    return [
        _ledger_evidence(
            document=document,
            condition_id=condition.id,
            text=text,
            page=page,
            anchor=str(anchor) if anchor is not None else None,
            role=EvidenceRole.supporting.value,
            source_tool=EvidenceSourceTool.doc_read.value,
            context=text,
        )
    ]


def _query_only_evidence(document: dict[str, Any], condition: ScreeningCondition) -> list[dict[str, Any]]:
    evidence = []
    for item in document["conditions"].get(condition.id, []):
        dumped = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        evidence.append(
            _ledger_evidence(
                document=document,
                condition_id=condition.id,
                text=str(dumped.get("text") or ""),
                page=_coerce_int(dumped.get("page")),
                anchor=None,
                role=EvidenceRole.retrieval_candidate.value,
                source_tool=EvidenceSourceTool.query.value,
                score=_coerce_float(dumped.get("score")),
                context=str(dumped.get("text") or ""),
            )
        )
    return [item for item in evidence if item["text"]]


def _judge_condition(llm: Any, plan: ScreeningPlanPayload, condition: ScreeningCondition, document: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        raw = llm.judge_condition(plan, condition, _serialize_document(document), evidence)
    except Exception as exc:
        raw = {"verdict": ConditionVerdictValue.unknown.value, "confidence": 0.0, "supporting_evidence": [], "contradicting_evidence": [], "missing_reason": str(exc)}
    return _normalize_raw_verdict(raw, evidence)


def _normalize_raw_verdict(raw: dict[str, Any], fallback_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    verdict = str(raw.get("verdict", ConditionVerdictValue.unknown.value))
    if verdict not in {item.value for item in ConditionVerdictValue}:
        verdict = ConditionVerdictValue.unknown.value
    supporting = _normalize_evidence_list(raw.get("supporting_evidence"), fallback_evidence)
    contradicting = _normalize_evidence_list(raw.get("contradicting_evidence"), [])
    missing_reason = raw.get("missing_reason")
    return {
        "verdict": verdict,
        "confidence": _clamp_confidence(raw.get("confidence", 0.0)),
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "missing_reason": str(missing_reason) if missing_reason is not None else None,
    }


def _persist_condition_verdict(
    session: Session,
    task: ScreeningTask,
    document: dict[str, Any],
    condition: ScreeningCondition,
    raw_verdict: dict[str, Any],
) -> ConditionVerdict:
    verdict = ConditionVerdict(
        task_id=task.id,
        document_uri=str(document["document_uri"]),
        condition_id=condition.id,
        verdict=raw_verdict["verdict"],
        confidence=raw_verdict["confidence"],
        supporting_evidence=raw_verdict["supporting_evidence"],
        contradicting_evidence=raw_verdict["contradicting_evidence"],
        missing_reason=raw_verdict["missing_reason"],
        verification_method=_enum_value(condition.verification_strategy),
    )
    session.add(verdict)
    return verdict


def _build_document_result(task: ScreeningTask, document: dict[str, Any], plan: ScreeningPlanPayload, verdicts: list[ConditionVerdict]) -> ScreeningDocumentResult:
    total = max(1, len(plan.conditions))
    supported = sum(1 for verdict in verdicts if verdict.supporting_evidence)
    support_rate = round(supported / total, 4)
    matched_conditions = [verdict.condition_id for verdict in verdicts if verdict.verdict == ConditionVerdictValue.satisfied.value]
    missing_conditions = [verdict.condition_id for verdict in verdicts if verdict.verdict in {ConditionVerdictValue.unknown.value, ConditionVerdictValue.conflicting.value}]
    decision, reason, uncertain_reasons = _document_decision(verdicts)
    evidence = [item for verdict in verdicts for item in verdict.supporting_evidence if item.get("used_for_decision")]
    confidence = round(sum(verdict.confidence for verdict in verdicts) / total, 4)
    return ScreeningDocumentResult(
        task_id=task.id,
        document_uri=str(document["document_uri"]),
        document_path=str(document["document_path"]),
        document_title=document["document_title"],
        collection=str(document["collection"]),
        decision=decision,
        reason=reason,
        matched_conditions=matched_conditions,
        missing_conditions=missing_conditions,
        evidence=evidence[:10],
        confidence=confidence,
        decision_basis={"condition_verdicts": [_condition_basis_item(verdict) for verdict in verdicts]},
        uncertain_reasons=uncertain_reasons,
        evidence_support_rate=support_rate,
        verification_status=VerificationStatus.deep_read_verified.value if support_rate == 1.0 else VerificationStatus.partially_verified.value,
    )


def _document_decision(verdicts: list[ConditionVerdict]) -> tuple[str, str, list[str]]:
    values = [verdict.verdict for verdict in verdicts]
    if values and all(value == ConditionVerdictValue.satisfied.value for value in values):
        return ResultDecision.included.value, "all_conditions_satisfied", []
    uncertain_reasons = []
    if ConditionVerdictValue.conflicting.value in values:
        uncertain_reasons.append(UncertainReason.conflicting_evidence.value)
    if ConditionVerdictValue.unknown.value in values:
        uncertain_reasons.append(UncertainReason.missing_evidence.value)
    if uncertain_reasons:
        return ResultDecision.uncertain.value, "condition_missing_or_conflicting", uncertain_reasons
    return ResultDecision.excluded.value, "condition_not_satisfied", []


def _ledger_evidence(
    *,
    document: dict[str, Any],
    condition_id: str,
    text: str,
    page: int | None,
    anchor: str | None,
    role: str,
    source_tool: str,
    context: str | None,
    score: float | None = None,
) -> dict[str, Any]:
    document_uri = str(document["document_uri"])
    return {
        "page": page,
        "text": text,
        "context": context,
        "source": "qmd",
        "score": score,
        "condition_id": condition_id,
        "artifact_ref": document_uri,
        "document_uri": document_uri,
        "role": role,
        "source_tool": source_tool,
        "document_path": str(document["document_path"]),
        "collection": str(document["collection"]),
        "anchor": anchor,
        "used_for_decision": True,
    }


def _first_match(payload: dict[str, Any]) -> dict[str, Any]:
    structured = payload.get("structuredContent") if isinstance(payload, dict) else None
    matches = structured.get("matches") if isinstance(structured, dict) else None
    if isinstance(matches, list) and matches and isinstance(matches[0], dict):
        return matches[0]
    return {}


def _normalize_evidence_list(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return list(fallback)
    return [item for item in value if isinstance(item, dict)]


def _condition_basis_item(verdict: ConditionVerdict) -> dict[str, Any]:
    return {
        "condition_id": verdict.condition_id,
        "verdict": verdict.verdict,
        "confidence": verdict.confidence,
        "supporting_evidence_count": len(verdict.supporting_evidence),
        "contradicting_evidence_count": len(verdict.contradicting_evidence),
        "missing_reason": verdict.missing_reason,
    }


def _serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    conditions = {}
    for condition_id, items in document["conditions"].items():
        conditions[condition_id] = [item.model_dump() if hasattr(item, "model_dump") else item for item in items]
    return {
        "document_uri": document["document_uri"],
        "document_path": document["document_path"],
        "document_title": document["document_title"],
        "collection": document["collection"],
        "conditions": conditions,
    }


def _clamp_confidence(value: Any) -> float:
    return max(0.0, min(1.0, _coerce_float(value) or 0.0))


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)
