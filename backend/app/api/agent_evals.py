from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.db import get_session
from app.enums import AuditEventType
from app.errors import ApiError
from app.models import AgentEvalRun
from app.services.audit import write_audit
from app.services.evals import compute_eval_metrics

router = APIRouter()


class AgentEvalRunRequest(BaseModel):
    cases: list[dict[str, Any]] = Field(min_length=1)
    schema_failures: int = 0
    verification_failures: int = 0


class AgentEvalRunResponse(BaseModel):
    run_id: UUID
    case_ids: list[Any]
    metrics: dict[str, float]
    failures: list[Any]
    created_at: datetime


@router.post("/run", response_model=AgentEvalRunResponse)
def run_agent_evals(
    payload: AgentEvalRunRequest,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
):
    metrics = compute_eval_metrics(payload.cases, schema_failures=payload.schema_failures, verification_failures=payload.verification_failures)
    run = AgentEvalRun(case_ids=[], metrics=metrics, failures=[])
    session.add(run)
    session.flush()
    write_audit(
        session,
        AuditEventType.agent_eval_run.value,
        {"run_id": str(run.id), "case_count": len(payload.cases), "schema_failures": payload.schema_failures, "verification_failures": payload.verification_failures},
        actor_id=auth.owner_id,
    )
    session.commit()
    return AgentEvalRunResponse(run_id=run.id, case_ids=run.case_ids, metrics=run.metrics, failures=run.failures, created_at=run.created_at)


@router.get("/{run_id}", response_model=AgentEvalRunResponse)
def get_agent_eval_run(run_id: UUID, session: Session = Depends(get_session)):
    run = session.get(AgentEvalRun, run_id)
    if run is None:
        raise ApiError("not_found", "Not found", 404)
    return AgentEvalRunResponse(run_id=run.id, case_ids=run.case_ids, metrics=run.metrics, failures=run.failures, created_at=run.created_at)
