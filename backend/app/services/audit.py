from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent, ScreeningTask

SENSITIVE_KEYS = {"authorization", "token", "stored_path", "contract_markdown", "raw_text"}


def sanitize_payload(payload: dict) -> dict:
    clean = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = sanitize_payload(value)
        elif isinstance(value, list):
            clean[key] = [sanitize_payload(v) if isinstance(v, dict) else v for v in value]
        else:
            clean[key] = value
    return clean


def write_audit(
    session: Session,
    event_type: str,
    payload: dict,
    *,
    actor_id: str | None = None,
    task: ScreeningTask | None = None,
    task_id: UUID | None = None,
    contract_id: UUID | None = None,
) -> AuditEvent:
    event = AuditEvent(
        task_id=task.id if task is not None else task_id,
        contract_id=contract_id,
        actor_id=actor_id if actor_id is not None else (task.owner_id if task is not None else None),
        event_type=event_type,
        payload=sanitize_payload(payload),
    )
    session.add(event)
    return event

