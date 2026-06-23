import asyncio
from time import monotonic
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.application.task_queue import enqueue_screening_task
from app.db import get_session, utcnow
from app.enums import AuditEventType, ResultDecision, ReviewStatus, TaskStatus
from app.errors import ApiError
from app.models import ScreeningDocumentResult, ScreeningTask, StreamEvent
from app.schemas import (
    CreateScreeningTaskRequest,
    CreateTaskResponse,
    DocumentResultItem,
    EvidenceItem,
    ResultBuckets,
    ReviewCounts,
    TaskCounts,
    TaskListItem,
    TaskListResponse,
    TaskResultsResponse,
    TaskSummaryResponse,
)
from app.services.audit import write_audit
from app.services.streaming import TERMINAL_EVENTS, append_stream_event, encode_sse, keepalive_sse, parse_last_event_id, snapshot_event

router = APIRouter()


@router.post("", response_model=CreateTaskResponse)
async def create_task(request: Request, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        raise ApiError("json_required", "Screening tasks must be created with a JSON request body", 415)
    payload = CreateScreeningTaskRequest.model_validate(await request.json())
    query = payload.query.strip()
    title = (payload.title or "").strip()
    if not query:
        raise ApiError("query_required", "Query is required", 400)
    if len(query) > 1000:
        raise ApiError("query_too_long", "Query is too long", 400)
    if title and len(title) > 120:
        raise ApiError("title_too_long", "Title is too long", 400)

    task = ScreeningTask(owner_id=auth.owner_id, title=title or query[:40], raw_query=query, status=TaskStatus.uploaded.value, current_stage=TaskStatus.uploaded.value, progress_percent=5, metrics={})
    session.add(task)
    session.flush()
    write_audit(session, AuditEventType.task_created.value, {"task_id": str(task.id), "title": task.title}, actor_id=auth.owner_id, task=task)
    append_stream_event(session, task.id, "task_created", {"task_id": str(task.id), "title": task.title})
    response_payload = CreateTaskResponse(task_id=task.id, title=task.title, raw_query=task.raw_query, status=TaskStatus(task.status), progress_percent=task.progress_percent, events_url=f"/api/screening-tasks/{task.id}/events", results_url=f"/api/screening-tasks/{task.id}/results")
    session.commit()

    try:
        rq_job_id = enqueue_screening_task(task.id)
    except Exception as exc:
        task = session.get(ScreeningTask, task.id)
        task.status = TaskStatus.failed.value
        task.current_stage = TaskStatus.failed.value
        task.error_code = "enqueue_failed"
        task.error_message = "Unable to enqueue screening task"
        task.completed_at = utcnow()
        write_audit(session, AuditEventType.task_failed.value, {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"}, actor_id=auth.owner_id, task=task)
        append_stream_event(session, task.id, "task_failed", {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"})
        session.commit()
        raise ApiError("enqueue_failed", "Unable to enqueue screening task", 503) from exc

    task = session.get(ScreeningTask, task.id)
    task.metrics = {"rq_job_id": rq_job_id}
    session.commit()
    return response_payload


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: str | None = None,
    q: str | None = None,
    sort: str = "created_desc",
    limit: int = 20,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    statement = select(ScreeningTask).where(ScreeningTask.owner_id == auth.owner_id)
    if status:
        if status == "active":
            statement = statement.where(ScreeningTask.status.in_([TaskStatus.uploaded.value, TaskStatus.retrieving.value, TaskStatus.classifying.value]))
        elif status in {item.value for item in TaskStatus}:
            statement = statement.where(ScreeningTask.status == status)
        else:
            raise ApiError("invalid_status", "Invalid task status filter", 400)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        statement = statement.where(or_(ScreeningTask.title.ilike(needle), ScreeningTask.raw_query.ilike(needle)))

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    if sort == "created_asc":
        statement = statement.order_by(ScreeningTask.created_at.asc())
    elif sort == "created_desc":
        statement = statement.order_by(ScreeningTask.created_at.desc())
    else:
        raise ApiError("invalid_sort", "Invalid task sort", 400)

    tasks = session.scalars(statement.limit(limit).offset(offset)).all()
    items = []
    for task in tasks:
        results = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).all()
        counts, review_counts = task_counts_for_results(results)
        items.append(
            TaskListItem(
                task_id=task.id,
                title=task.title,
                raw_query=task.raw_query,
                status=TaskStatus(task.status),
                progress_percent=task.progress_percent,
                current_stage=task.current_stage,
                error_code=task.error_code,
                error_message=task.error_message,
                created_at=task.created_at,
                updated_at=task.updated_at,
                completed_at=task.completed_at,
                counts=counts,
                review_counts=review_counts,
            )
        )
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{task_id}/copy", response_model=CreateTaskResponse)
def copy_task(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    source = load_owned_task(session, task_id, auth)
    copied_from_task_id = str(source.id)
    task = ScreeningTask(
        owner_id=auth.owner_id,
        title=source.title,
        raw_query=source.raw_query,
        status=TaskStatus.uploaded.value,
        current_stage=TaskStatus.uploaded.value,
        progress_percent=5,
        metrics={"copied_from_task_id": copied_from_task_id},
    )
    session.add(task)
    session.flush()
    write_audit(session, AuditEventType.task_created.value, {"task_id": str(task.id), "title": task.title, "copied_from_task_id": copied_from_task_id}, actor_id=auth.owner_id, task=task)
    append_stream_event(session, task.id, "task_created", {"task_id": str(task.id), "title": task.title, "copied_from_task_id": copied_from_task_id})
    response_payload = CreateTaskResponse(task_id=task.id, title=task.title, raw_query=task.raw_query, status=TaskStatus(task.status), progress_percent=task.progress_percent, events_url=f"/api/screening-tasks/{task.id}/events", results_url=f"/api/screening-tasks/{task.id}/results")
    session.commit()

    try:
        rq_job_id = enqueue_screening_task(task.id)
    except Exception as exc:
        task = session.get(ScreeningTask, task.id)
        task.status = TaskStatus.failed.value
        task.current_stage = TaskStatus.failed.value
        task.error_code = "enqueue_failed"
        task.error_message = "Unable to enqueue screening task"
        task.completed_at = utcnow()
        write_audit(session, AuditEventType.task_failed.value, {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"}, actor_id=auth.owner_id, task=task)
        append_stream_event(session, task.id, "task_failed", {"task_id": str(task.id), "stage": "uploaded", "error_code": "enqueue_failed", "message": "Unable to enqueue screening task"})
        session.commit()
        raise ApiError("enqueue_failed", "Unable to enqueue screening task", 503) from exc

    task = session.get(ScreeningTask, task.id)
    task.metrics = {"copied_from_task_id": copied_from_task_id, "rq_job_id": rq_job_id}
    session.commit()
    return response_payload


@router.get("/{task_id}", response_model=TaskSummaryResponse)
def get_task(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    return task_summary(session, task)


@router.get("/{task_id}/results", response_model=TaskResultsResponse)
def get_results(task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    buckets = ResultBuckets(included=[], uncertain=[], excluded=[])
    results = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).all()
    for result in results:
        item = DocumentResultItem(
            result_id=result.id,
            document_uri=result.document_uri,
            document_path=result.document_path,
            document_title=result.document_title,
            collection=result.collection,
            decision=ResultDecision(result.decision),
            reason=result.reason,
            matched_conditions=result.matched_conditions,
            missing_conditions=result.missing_conditions,
            evidence=[EvidenceItem(**e) for e in result.evidence],
            confidence=result.confidence,
            review_status=ReviewStatus(result.review_status),
            review_decision=ResultDecision(result.review_decision) if result.review_decision else None,
            review_note=result.review_note,
            reviewer_name=result.reviewer_name,
            reviewed_at=result.reviewed_at,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )
        getattr(buckets, result.decision).append(item)
    return TaskResultsResponse(task_id=task.id, buckets=buckets)


@router.get("/{task_id}/events")
async def events(request: Request, task_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = load_owned_task(session, task_id, auth)
    last_sequence = parse_last_event_id(request.headers.get("Last-Event-ID"), task.id)

    async def generate():
        nonlocal last_sequence
        last_keepalive = monotonic()
        if last_sequence is None:
            yield snapshot_event(task)
            last_sequence = 0
        while True:
            latest_terminal = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id, StreamEvent.event_type.in_(TERMINAL_EVENTS)).order_by(StreamEvent.sequence.desc())).first()
            if latest_terminal and last_sequence >= latest_terminal.sequence:
                return
            events_to_send = session.scalars(select(StreamEvent).where(StreamEvent.task_id == task.id, StreamEvent.sequence > last_sequence).order_by(StreamEvent.sequence.asc())).all()
            for event in events_to_send:
                yield encode_sse(event)
                last_sequence = event.sequence
                if event.event_type in TERMINAL_EVENTS:
                    return
            if await request.is_disconnected():
                return
            from app.config import settings

            if monotonic() - last_keepalive >= settings.SSE_KEEPALIVE_SECONDS:
                yield keepalive_sse()
                last_keepalive = monotonic()
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


def load_owned_task(session: Session, task_id: UUID, auth: AuthContext) -> ScreeningTask:
    task = session.get(ScreeningTask, task_id)
    if task is None:
        raise ApiError("not_found", "Not found", 404)
    if task.owner_id != auth.owner_id:
        write_audit(session, AuditEventType.permission_denied.value, {"resource_type": "screening_task", "resource_id": str(task_id), "reason": "owner_mismatch"}, actor_id=auth.owner_id, task_id=task_id)
        session.commit()
        raise ApiError("not_found", "Not found", 404)
    return task


def task_summary(session: Session, task: ScreeningTask) -> TaskSummaryResponse:
    results = session.scalars(select(ScreeningDocumentResult).where(ScreeningDocumentResult.task_id == task.id)).all()
    counts, _ = task_counts_for_results(results)
    return TaskSummaryResponse(task_id=task.id, title=task.title, raw_query=task.raw_query, status=TaskStatus(task.status), progress_percent=task.progress_percent, current_stage=task.current_stage, error_code=task.error_code, error_message=task.error_message, created_at=task.created_at, updated_at=task.updated_at, completed_at=task.completed_at, counts=counts)


def task_counts_for_results(results: list[ScreeningDocumentResult]) -> tuple[TaskCounts, ReviewCounts]:
    counts = TaskCounts(
        documents=len(results),
        included=sum(1 for r in results if r.decision == ResultDecision.included.value),
        uncertain=sum(1 for r in results if r.decision == ResultDecision.uncertain.value),
        excluded=sum(1 for r in results if r.decision == ResultDecision.excluded.value),
    )
    review_counts = ReviewCounts(
        reviewed=sum(1 for r in results if r.review_status == ReviewStatus.reviewed.value),
        unreviewed=sum(1 for r in results if r.review_status == ReviewStatus.unreviewed.value),
    )
    return counts, review_counts
