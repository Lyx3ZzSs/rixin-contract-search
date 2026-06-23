import csv
import io
from datetime import date, datetime

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask, StreamEvent

EXPORT_COLUMNS = [
    "task_id",
    "task_title",
    "raw_query",
    "task_created_at",
    "task_completed_at",
    "document_uri",
    "document_path",
    "document_title",
    "collection",
    "agent_decision",
    "agent_reason",
    "confidence",
    "matched_conditions",
    "missing_conditions",
    "review_status",
    "review_decision",
    "review_note",
    "reviewer_name",
    "reviewed_at",
    "evidence_summary",
]


def _value(value):
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(_value(item) for item in value)
    return str(value)


def evidence_summary(evidence):
    summaries = []
    for item in evidence or []:
        condition_id = item.get("condition_id")
        score = item.get("score")
        text = " ".join(str(item.get("text", "")).split())
        parts = []
        if condition_id:
            parts.append(f"condition={condition_id}")
        if score is not None:
            parts.append(f"score={score}")
        if text:
            parts.append(text)
        if parts:
            summaries.append(" | ".join(parts))
    return "\n".join(summaries)


def export_rows(task: ScreeningTask, results: list[ScreeningDocumentResult]):
    return [
        {
            "task_id": _value(task.id),
            "task_title": _value(task.title),
            "raw_query": _value(task.raw_query),
            "task_created_at": _value(task.created_at),
            "task_completed_at": _value(task.completed_at),
            "document_uri": _value(result.document_uri),
            "document_path": _value(result.document_path),
            "document_title": _value(result.document_title),
            "collection": _value(result.collection),
            "agent_decision": _value(result.decision),
            "agent_reason": _value(result.reason),
            "confidence": _value(result.confidence),
            "matched_conditions": _value(result.matched_conditions),
            "missing_conditions": _value(result.missing_conditions),
            "review_status": _value(result.review_status),
            "review_decision": _value(result.review_decision),
            "review_note": _value(result.review_note),
            "reviewer_name": _value(result.reviewer_name),
            "reviewed_at": _value(result.reviewed_at),
            "evidence_summary": evidence_summary(result.evidence),
        }
        for result in results
    ]


def build_csv(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(export_rows(task, results))
    return output.getvalue()


def build_xlsx(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Screening Results"
    worksheet.append(EXPORT_COLUMNS)
    for row in export_rows(task, results):
        worksheet.append([row[column] for column in EXPORT_COLUMNS])

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_json(session: Session, task: ScreeningTask, results: list[ScreeningDocumentResult]) -> dict:
    plan = session.scalar(select(ScreeningPlan).where(ScreeningPlan.task_id == task.id))
    events = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id).order_by(StreamEvent.sequence.asc())).all()
    return {
        "task": {
            "task_id": str(task.id),
            "title": task.title,
            "raw_query": task.raw_query,
            "status": task.status,
            "current_stage": task.current_stage,
            "progress_percent": task.progress_percent,
            "metrics": task.metrics,
            "created_at": _value(task.created_at),
            "updated_at": _value(task.updated_at),
            "completed_at": _value(task.completed_at),
        },
        "plan": plan.plan_json if plan else None,
        "results": [
            {
                "result_id": str(result.id),
                "document_uri": result.document_uri,
                "document_path": result.document_path,
                "document_title": result.document_title,
                "collection": result.collection,
                "agent_decision": result.decision,
                "agent_reason": result.reason,
                "matched_conditions": result.matched_conditions,
                "missing_conditions": result.missing_conditions,
                "evidence": result.evidence,
                "confidence": result.confidence,
                "review_status": result.review_status,
                "review_decision": result.review_decision,
                "review_note": result.review_note,
                "reviewer_name": result.reviewer_name,
                "reviewed_at": _value(result.reviewed_at),
                "created_at": _value(result.created_at),
                "updated_at": _value(result.updated_at),
            }
            for result in results
        ],
        "events": [
            {
                "sequence": event.sequence,
                "type": event.event_type,
                "payload": event.payload,
                "created_at": _value(event.created_at),
            }
            for event in events
        ],
    }
