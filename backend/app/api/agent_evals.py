from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.db import get_session
from app.enums import AuditEventType, ResultDecision, VerificationStatus
from app.errors import ApiError
from app.models import AgentEvalCase as AgentEvalCaseRow, AgentEvalRun, AuditEvent
from app.services.audit import write_audit
from app.services.evals import compute_eval_metrics

router = APIRouter()


class AgentEvalPrediction(BaseModel):
    document_uri: str
    decision: ResultDecision
    evidence_support_rate: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus

    @field_validator("document_uri")
    @classmethod
    def normalize_document_uri(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("document_uri is required")
        return value


class AgentEvalExpected(BaseModel):
    included: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)

    @field_validator("included", "excluded", "uncertain")
    @classmethod
    def normalize_uri_list(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for document_uri in value:
            document_uri = document_uri.strip()
            if not document_uri:
                raise ValueError("document_uri entries are required")
            normalized.append(document_uri)
        return normalized


class AgentEvalCase(BaseModel):
    name: str | None = None
    raw_query: str | None = None
    expected: AgentEvalExpected = Field(default_factory=AgentEvalExpected)
    actual: list[AgentEvalPrediction] = Field(default_factory=list)


class AgentEvalRunRequest(BaseModel):
    cases: list[AgentEvalCase] = Field(min_length=1)
    schema_failures: int = Field(default=0, ge=0)
    verification_failures: int = Field(default=0, ge=0)
    failures: list[dict] = Field(default_factory=list)


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
    case_rows = []
    for case in payload.cases:
        case_rows.append(
            AgentEvalCaseRow(
                name=case.name or case.raw_query or "agent-eval-case",
                raw_query=case.raw_query or case.name or "",
                expected={"expected": case.expected.model_dump(), "actual": [prediction.model_dump() for prediction in case.actual]},
            )
        )
    session.add_all(case_rows)
    session.flush()

    run = AgentEvalRun(case_ids=[str(case.id) for case in case_rows], metrics=metrics, failures=payload.failures)
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
def get_agent_eval_run(run_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    audit_events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.event_type == AuditEventType.agent_eval_run.value,
            AuditEvent.actor_id == auth.owner_id,
        )
    ).all()
    if not any(str(event.payload.get("run_id") or "") == str(run_id) for event in audit_events):
        raise ApiError("not_found", "Not found", 404)
    run = session.get(AgentEvalRun, run_id)
    if run is None:
        raise ApiError("not_found", "Not found", 404)
    return AgentEvalRunResponse(run_id=run.id, case_ids=run.case_ids, metrics=run.metrics, failures=run.failures, created_at=run.created_at)
