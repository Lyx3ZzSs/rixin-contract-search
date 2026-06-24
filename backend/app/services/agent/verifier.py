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
            evidence, evidence_reason = _gather_evidence(qmd, document, condition)
            raw_verdict = _judge_condition(llm, plan, condition, document, evidence, evidence_reason)
            verdict = _persist_condition_verdict(session, task, document, condition, raw_verdict)
            verdicts.append(verdict)
        session.add(_build_document_result(task, document, plan, verdicts))
    return len(documents)


def _gather_evidence(qmd: Any, document: dict[str, Any], condition: ScreeningCondition) -> tuple[list[dict[str, Any]], str | None]:
    strategy = _enum_value(condition.verification_strategy)
    if strategy == VerificationStrategy.grep_then_read.value:
        return _grep_then_read_evidence(qmd, document, condition)
    if strategy == VerificationStrategy.query_only.value:
        return _query_only_evidence(document, condition)
    if strategy in {VerificationStrategy.doc_query.value, VerificationStrategy.toc_guided_read.value}:
        return [], "unsupported_verification_strategy"
    return [], "unsupported_verification_strategy"


def _grep_then_read_evidence(qmd: Any, document: dict[str, Any], condition: ScreeningCondition) -> tuple[list[dict[str, Any]], str | None]:
    document_uri = str(document["document_uri"])
    query_text = condition.qmd_queries[0] if condition.qmd_queries else condition.description
    try:
        grep_payload = qmd.doc_grep(document_uri, query_text)
        first = _first_match(grep_payload)
        if not first:
            return [], "verification_failed"
        read_payload = qmd.doc_read(document_uri, page=first.get("page"), anchor=first.get("anchor"), window=2)
    except Exception:
        return [], "verification_failed"
    structured = read_payload.get("structuredContent") if isinstance(read_payload, dict) else None
    structured = structured if isinstance(structured, dict) else {}
    text = str(structured.get("text") or first.get("text") or "").strip()
    if not text:
        return [], "verification_failed"
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
    ], None


def _query_only_evidence(document: dict[str, Any], condition: ScreeningCondition) -> tuple[list[dict[str, Any]], str | None]:
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
    return [item for item in evidence if item["text"]], None


def _judge_condition(
    llm: Any,
    plan: ScreeningPlanPayload,
    condition: ScreeningCondition,
    document: dict[str, Any],
    evidence: list[dict[str, Any]],
    evidence_reason: str | None,
) -> dict[str, Any]:
    try:
        raw = llm.judge_condition(plan, condition, _serialize_document(document), evidence)
    except Exception as exc:
        raw = {"verdict": ConditionVerdictValue.unknown.value, "confidence": 0.0, "supporting_evidence": [], "contradicting_evidence": [], "missing_reason": str(exc)}
    return _normalize_raw_verdict(raw, evidence, evidence_reason, condition)


def _normalize_raw_verdict(
    raw: dict[str, Any],
    fallback_evidence: list[dict[str, Any]],
    evidence_reason: str | None,
    condition: ScreeningCondition,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    verdict = str(raw.get("verdict", ConditionVerdictValue.unknown.value))
    if verdict not in {item.value for item in ConditionVerdictValue}:
        verdict = ConditionVerdictValue.unknown.value
    supporting = _normalize_evidence_list(
        raw.get("supporting_evidence"),
        fallback_evidence,
        allow_fallback_when_unmatched=verdict == ConditionVerdictValue.satisfied.value,
    )
    contradicting = _normalize_evidence_list(raw.get("contradicting_evidence"), fallback_evidence)
    missing_reason = raw.get("missing_reason")
    required_evidence_count = max(1, int(getattr(condition, "required_evidence_count", 1) or getattr(condition, "evidence_required", 1) or 1))
    trusted_supporting_count = len(supporting)

    if not supporting:
        if evidence_reason == "verification_failed":
            verdict = ConditionVerdictValue.unknown.value
            missing_reason = missing_reason or evidence_reason
        elif evidence_reason == "unsupported_verification_strategy":
            verdict = ConditionVerdictValue.unknown.value
            missing_reason = missing_reason or evidence_reason
        elif verdict == ConditionVerdictValue.satisfied.value:
            verdict = ConditionVerdictValue.unknown.value
            missing_reason = missing_reason or "supporting_evidence_required"
        elif missing_reason is None:
            missing_reason = evidence_reason or "supporting_evidence_required"
    elif verdict == ConditionVerdictValue.satisfied.value and trusted_supporting_count < required_evidence_count:
        verdict = ConditionVerdictValue.unknown.value
        missing_reason = "insufficient_supporting_evidence"
    if verdict == ConditionVerdictValue.unknown.value and not supporting and missing_reason is None:
        missing_reason = "supporting_evidence_required"
    confidence = _clamp_confidence(raw.get("confidence", 0.0))
    if verdict == ConditionVerdictValue.unknown.value and (not supporting or trusted_supporting_count < required_evidence_count):
        confidence = 0.0
    return {
        "verdict": verdict,
        "confidence": confidence,
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
    condition_requirements = {condition.id: max(1, int(condition.required_evidence_count or condition.evidence_required or 1)) for condition in plan.conditions}
    supported = sum(
        1
        for verdict in verdicts
        if verdict.verdict == ConditionVerdictValue.satisfied.value
        and len(verdict.supporting_evidence) >= condition_requirements.get(verdict.condition_id, 1)
    )
    support_rate = round(supported / total, 4)
    matched_conditions = [verdict.condition_id for verdict in verdicts if verdict.verdict == ConditionVerdictValue.satisfied.value]
    missing_conditions = [verdict.condition_id for verdict in verdicts if verdict.verdict in {ConditionVerdictValue.unknown.value, ConditionVerdictValue.conflicting.value}]
    decision, reason, uncertain_reasons = _document_decision(verdicts)
    evidence = [item for verdict in verdicts for item in verdict.supporting_evidence if item.get("used_for_decision")]
    confidence = round(sum(verdict.confidence for verdict in verdicts) / total, 4)
    verification_status = _verification_status(verdicts, support_rate)
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
        verification_status=verification_status,
    )


def _verification_status(verdicts: list[ConditionVerdict], support_rate: float) -> str:
    if any(verdict.missing_reason in {"verification_failed", "unsupported_verification_strategy"} for verdict in verdicts):
        return VerificationStatus.verification_failed.value

    if support_rate < 1.0:
        return VerificationStatus.partially_verified.value

    if not verdicts:
        return VerificationStatus.query_only.value

    evidence_items = [item for verdict in verdicts for item in verdict.supporting_evidence if item.get("used_for_decision")]
    if not evidence_items:
        return VerificationStatus.query_only.value

    source_tools = {str(item.get("source_tool")) for item in evidence_items if item.get("source_tool")}
    if source_tools and source_tools <= {EvidenceSourceTool.query.value}:
        return VerificationStatus.query_only.value

    deep_read_tools = {
        EvidenceSourceTool.doc_read.value,
        EvidenceSourceTool.doc_query.value,
        EvidenceSourceTool.doc_grep.value,
        EvidenceSourceTool.doc_elements.value,
    }
    if source_tools and source_tools <= deep_read_tools:
        return VerificationStatus.deep_read_verified.value

    return VerificationStatus.partially_verified.value


def _document_decision(verdicts: list[ConditionVerdict]) -> tuple[str, str, list[str]]:
    values = [verdict.verdict for verdict in verdicts]
    if values and all(value == ConditionVerdictValue.satisfied.value for value in values):
        return ResultDecision.included.value, "all_conditions_satisfied", []
    uncertain_reasons = []
    if ConditionVerdictValue.conflicting.value in values:
        uncertain_reasons.append(UncertainReason.conflicting_evidence.value)
    if ConditionVerdictValue.unknown.value in values:
        uncertain_reasons.append(UncertainReason.missing_evidence.value)
    if any(verdict.missing_reason in {"verification_failed", "unsupported_verification_strategy"} for verdict in verdicts):
        uncertain_reasons.append(UncertainReason.verification_failed.value)
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


def _normalize_evidence_list(
    value: Any,
    fallback: list[dict[str, Any]],
    *,
    allow_fallback_when_unmatched: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return list(fallback) if allow_fallback_when_unmatched else []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        resolved = _resolve_evidence_item(item, fallback)
        if resolved is not None:
            normalized.append(resolved)
    if normalized:
        return normalized
    return list(fallback) if allow_fallback_when_unmatched else []


def _resolve_evidence_item(item: dict[str, Any], fallback: list[dict[str, Any]]) -> dict[str, Any] | None:
    for candidate in fallback:
        if _evidence_matches(item, candidate):
            return candidate
    return None


def _evidence_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    shared_identifiers = False
    for key in ("artifact_ref", "document_uri", "condition_id", "source_tool", "page", "anchor", "text", "context"):
        if key not in left or left.get(key) is None:
            continue
        shared_identifiers = True
        if not _evidence_field_matches(key, left.get(key), right.get(key)):
            return False
    return shared_identifiers


def _evidence_field_matches(key: str, left_value: Any, right_value: Any) -> bool:
    if key == "page":
        return _coerce_int(left_value) == _coerce_int(right_value)
    if key in {"artifact_ref", "document_uri", "condition_id", "source_tool", "anchor", "text", "context"}:
        return _normalized_evidence_text(left_value) == _normalized_evidence_text(right_value)
    return left_value == right_value


def _normalized_evidence_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


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
