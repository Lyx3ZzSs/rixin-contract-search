import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import ScreeningTask, StreamEvent

TERMINAL_EVENTS = {"task_completed", "task_failed"}


def append_stream_event(session: Session, task_id: UUID, event_type: str, payload: dict) -> StreamEvent:
    sequence = session.scalar(select(func.coalesce(func.max(StreamEvent.sequence), 0)).where(StreamEvent.task_id == task_id)) + 1
    event = StreamEvent(task_id=task_id, sequence=sequence, event_type=event_type, payload=payload)
    session.add(event)
    session.flush()
    return event


def event_id(task_id: UUID, sequence: int) -> str:
    return f"{task_id}:{sequence}"


def encode_sse(event: StreamEvent) -> str:
    data = {
        "event_id": event_id(event.task_id, event.sequence),
        "type": event.event_type,
        "task_id": str(event.task_id),
        "timestamp": event.created_at.isoformat(),
        "payload": event.payload,
    }
    return f"id: {data['event_id']}\nevent: {event.event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def keepalive_sse() -> str:
    return ": keepalive\n\n"


def snapshot_event(task: ScreeningTask, sequence: int = 0) -> str:
    data = {
        "event_id": event_id(task.id, sequence),
        "type": "snapshot",
        "task_id": str(task.id),
        "timestamp": utcnow().isoformat(),
        "payload": {
            "status": task.status,
            "progress_percent": task.progress_percent,
            "current_stage": task.current_stage,
            "counts": {},
        },
    }
    return f"id: {data['event_id']}\nevent: snapshot\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_last_event_id(value: str | None, task_id: UUID) -> int | None:
    if not value:
        return None
    try:
        raw_task_id, raw_sequence = value.split(":", 1)
        if UUID(raw_task_id) != task_id:
            return None
        sequence = int(raw_sequence)
        if sequence < 0:
            return None
        return sequence
    except Exception:
        return None
