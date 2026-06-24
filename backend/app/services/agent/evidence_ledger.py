from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import EvidenceRole, EvidenceSourceTool
from app.models import ScreeningDocumentResult


def build_evidence_ledger(session: Session, task_id: UUID) -> list[dict[str, Any]]:
    results = session.scalars(
        select(ScreeningDocumentResult)
        .where(ScreeningDocumentResult.task_id == task_id)
        .order_by(ScreeningDocumentResult.document_uri.asc(), ScreeningDocumentResult.created_at.asc())
    ).all()
    items: list[dict[str, Any]] = []
    for result in results:
        for raw_item in _iter_raw_evidence(result.evidence):
            items.append(
                normalize_ledger_evidence_item(
                    raw_item,
                    document_uri=result.document_uri,
                    document_path=result.document_path,
                    collection=result.collection,
                )
            )
    return items


def normalize_ledger_evidence_item(
    raw_item: dict[str, Any],
    *,
    document_uri: str | None = None,
    document_path: str | None = None,
    collection: str | None = None,
) -> dict[str, Any]:
    item = dict(raw_item)
    if not item.get("source"):
        item["source"] = "qmd"
    if not item.get("role"):
        item["role"] = EvidenceRole.retrieval_candidate.value
    if not item.get("source_tool"):
        item["source_tool"] = EvidenceSourceTool.query.value
    if document_uri is not None and not item.get("document_uri"):
        item["document_uri"] = document_uri
    if document_path is not None and not item.get("document_path"):
        item["document_path"] = document_path
    if collection is not None and not item.get("collection"):
        item["collection"] = collection
    if "used_for_decision" not in item or item["used_for_decision"] is None:
        item["used_for_decision"] = item.get("role") == EvidenceRole.supporting.value
    return item


def _iter_raw_evidence(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return (item for item in value if isinstance(item, dict))
