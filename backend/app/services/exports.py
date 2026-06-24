import csv
import io
import json
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
    "decision_basis",
    "uncertain_reasons",
    "evidence_support_rate",
    "verification_status",
    "review_status",
    "review_decision",
    "review_note",
    "reviewer_name",
    "reviewed_at",
    "evidence_summary",
]

EXPORT_HEADER_LABELS = {
    "task_id": "任务ID",
    "task_title": "任务标题",
    "raw_query": "原始问题",
    "task_created_at": "任务创建时间",
    "task_completed_at": "任务完成时间",
    "document_uri": "文档URI",
    "document_path": "文档路径",
    "document_title": "文档标题",
    "collection": "集合",
    "agent_decision": "系统判定",
    "agent_reason": "系统理由",
    "confidence": "置信度",
    "matched_conditions": "命中条件",
    "missing_conditions": "缺失条件",
    "decision_basis": "条件级判断",
    "uncertain_reasons": "不确定原因",
    "evidence_support_rate": "证据支持率",
    "verification_status": "核验状态",
    "review_status": "复核状态",
    "review_decision": "复核判定",
    "review_note": "复核备注",
    "reviewer_name": "复核人",
    "reviewed_at": "复核时间",
    "evidence_summary": "证据摘要",
}

SPREADSHEET_HEADERS = [EXPORT_HEADER_LABELS[column] for column in EXPORT_COLUMNS]

DANGEROUS_SPREADSHEET_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _value(value):
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(_value(item) for item in value)
    return str(value)


def _spreadsheet_value(value):
    text = _value(value)
    if text.startswith(DANGEROUS_SPREADSHEET_PREFIXES):
        return f"'{text}"
    return text


def _json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
    task_values = {
        "task_id": _value(task.id),
        "task_title": _value(task.title),
        "raw_query": _value(task.raw_query),
        "task_created_at": _value(task.created_at),
        "task_completed_at": _value(task.completed_at),
    }
    if not results:
        return [{**task_values, **{column: "" for column in EXPORT_COLUMNS if column not in task_values}}]
    return [
        {
            **task_values,
            "document_uri": _value(result.document_uri),
            "document_path": _value(result.document_path),
            "document_title": _value(result.document_title),
            "collection": _value(result.collection),
            "agent_decision": _value(result.decision),
            "agent_reason": _value(result.reason),
            "confidence": _value(result.confidence),
            "matched_conditions": _value(result.matched_conditions),
            "missing_conditions": _value(result.missing_conditions),
            "decision_basis": _json_value(result.decision_basis),
            "uncertain_reasons": _value(result.uncertain_reasons),
            "evidence_support_rate": _value(result.evidence_support_rate),
            "verification_status": _value(result.verification_status),
            "review_status": _value(result.review_status),
            "review_decision": _value(result.review_decision),
            "review_note": _value(result.review_note),
            "reviewer_name": _value(result.reviewer_name),
            "reviewed_at": _value(result.reviewed_at),
            "evidence_summary": evidence_summary(result.evidence),
        }
        for result in results
    ]


def spreadsheet_rows(task: ScreeningTask, results: list[ScreeningDocumentResult]):
    return [{EXPORT_HEADER_LABELS[column]: _spreadsheet_value(row[column]) for column in EXPORT_COLUMNS} for row in export_rows(task, results)]


def build_csv(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=SPREADSHEET_HEADERS)
    writer.writeheader()
    writer.writerows(spreadsheet_rows(task, results))
    return output.getvalue()


def build_xlsx(task: ScreeningTask, results: list[ScreeningDocumentResult]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Screening Results"
    worksheet.append(SPREADSHEET_HEADERS)
    for row in spreadsheet_rows(task, results):
        worksheet.append([row[header] for header in SPREADSHEET_HEADERS])

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
            "error_code": task.error_code,
            "error_message": task.error_message,
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
                "decision_basis": result.decision_basis,
                "uncertain_reasons": result.uncertain_reasons,
                "evidence_support_rate": result.evidence_support_rate,
                "verification_status": result.verification_status,
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
