from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QmdCandidateSnippet
from app.schemas import EvidenceItem, ScreeningPlanPayload


def aggregate_candidates(session: Session, task_id: UUID, plan: ScreeningPlanPayload) -> dict[UUID, dict[str, list[EvidenceItem]]]:
    rows = session.scalars(select(QmdCandidateSnippet).where(QmdCandidateSnippet.task_id == task_id, QmdCandidateSnippet.contract_id.is_not(None))).all()
    output: dict[UUID, dict[str, list[EvidenceItem]]] = defaultdict(lambda: defaultdict(list))
    seen = set()
    for condition in plan.conditions:
        condition_rows = [row for row in rows if row.condition_id == condition.id and not row.is_weak]
        for row in condition_rows:
            key = (row.contract_id, row.condition_id, row.artifact_ref, row.page_number, " ".join(row.snippet_text.split()).lower())
            if key in seen:
                continue
            seen.add(key)
            bucket = output[row.contract_id][condition.id]
            if len(bucket) >= 5:
                continue
            bucket.append(EvidenceItem(page=row.page_number, text=row.snippet_text, score=row.score, condition_id=row.condition_id, artifact_ref=row.artifact_ref))
    return output


def aggregate_document_candidates(session: Session, task_id: UUID, plan: ScreeningPlanPayload) -> dict[str, dict[str, object]]:
    rows = session.scalars(select(QmdCandidateSnippet).where(QmdCandidateSnippet.task_id == task_id, QmdCandidateSnippet.document_uri.is_not(None))).all()
    output: dict[str, dict[str, object]] = {}
    seen = set()
    for condition in plan.conditions:
        condition_rows = [row for row in rows if row.condition_id == condition.id and not row.is_weak]
        for row in condition_rows:
            key = (row.document_uri, row.condition_id, row.artifact_ref, row.page_number, " ".join(row.snippet_text.split()).lower())
            if key in seen:
                continue
            seen.add(key)
            document = output.setdefault(
                row.document_uri,
                {
                    "document_uri": row.document_uri,
                    "document_path": row.document_path or row.document_uri,
                    "document_title": row.document_title,
                    "collection": row.collection or "",
                    "conditions": defaultdict(list),
                },
            )
            bucket = document["conditions"][condition.id]
            if len(bucket) >= 5:
                continue
            bucket.append(EvidenceItem(page=row.page_number, text=row.snippet_text, score=row.score, condition_id=row.condition_id, artifact_ref=row.artifact_ref))
    return output
