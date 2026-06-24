from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EvidenceRole, EvidenceSourceTool
from app.models import ConditionVerdict, ScreeningDocumentResult


def build_evidence_ledger(session: Session, task_id: UUID) -> list[dict[str, Any]]:
    results = session.scalars(
        select(ScreeningDocumentResult)
        .where(ScreeningDocumentResult.task_id == task_id)
        .order_by(ScreeningDocumentResult.document_uri.asc(), ScreeningDocumentResult.created_at.asc())
    ).all()
    verdicts = session.scalars(
        select(ConditionVerdict)
        .where(ConditionVerdict.task_id == task_id)
        .order_by(ConditionVerdict.document_uri.asc(), ConditionVerdict.condition_id.asc(), ConditionVerdict.created_at.asc())
    ).all()
    result_by_uri = {result.document_uri: result for result in results}
    items: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for result in results:
        for raw_item in _iter_raw_evidence(result.evidence):
            item = normalize_ledger_evidence_item(
                raw_item,
                document_uri=result.document_uri,
                document_path=result.document_path,
                collection=result.collection,
                role=EvidenceRole.supporting.value,
                used_for_decision=True,
            )
            _append_deduped_item(items, seen_keys, item)
    for verdict in verdicts:
        result = result_by_uri.get(verdict.document_uri)
        for raw_item in _iter_raw_evidence(verdict.supporting_evidence):
            item = normalize_ledger_evidence_item(
                raw_item,
                document_uri=verdict.document_uri,
                document_path=result.document_path if result is not None else None,
                collection=result.collection if result is not None else None,
                role=EvidenceRole.supporting.value,
                used_for_decision=True,
                condition_id=verdict.condition_id,
            )
            _append_deduped_item(items, seen_keys, item)
        for raw_item in _iter_raw_evidence(verdict.contradicting_evidence):
            item = normalize_ledger_evidence_item(
                raw_item,
                document_uri=verdict.document_uri,
                document_path=result.document_path if result is not None else None,
                collection=result.collection if result is not None else None,
                role=EvidenceRole.contradicting.value,
                used_for_decision=True,
                condition_id=verdict.condition_id,
            )
            _append_deduped_item(items, seen_keys, item)
    return items


def normalize_ledger_evidence_item(
    raw_item: dict[str, Any],
    *,
    document_uri: str | None = None,
    document_path: str | None = None,
    collection: str | None = None,
    role: str | None = None,
    used_for_decision: bool | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    item = dict(raw_item)
    item.update({key: value for key, value in extra_fields.items() if value is not None and key not in item})
    if not item.get("source"):
        item["source"] = "qmd"
    if role is not None:
        item["role"] = role
    elif not item.get("role"):
        item["role"] = EvidenceRole.supporting.value
    if not item.get("source_tool"):
        item["source_tool"] = EvidenceSourceTool.query.value
    if document_uri is not None and not item.get("document_uri"):
        item["document_uri"] = document_uri
    if document_path is not None and not item.get("document_path"):
        item["document_path"] = document_path
    if collection is not None and not item.get("collection"):
        item["collection"] = collection
    if used_for_decision is not None:
        item["used_for_decision"] = used_for_decision
    elif "used_for_decision" not in item or item["used_for_decision"] is None:
        item["used_for_decision"] = item.get("role") == EvidenceRole.supporting.value
    return item


def _iter_raw_evidence(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return (item for item in value if isinstance(item, dict))


def _append_deduped_item(items: list[dict[str, Any]], seen_keys: set[tuple[Any, ...]], item: dict[str, Any]) -> None:
    key = _ledger_item_key(item)
    if key in seen_keys:
        return
    seen_keys.add(key)
    items.append(item)


def _ledger_item_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _normalized_key_value(item.get("document_uri") or item.get("artifact_ref")),
        _normalized_key_value(item.get("condition_id")),
        _normalized_key_value(item.get("role")),
        _normalized_key_value(item.get("source_tool")),
        _normalized_key_value(item.get("page")),
        _normalized_key_value(item.get("anchor")),
        _normalized_key_value(item.get("text")),
        _normalized_key_value(item.get("context")),
    )


def _normalized_key_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return value
