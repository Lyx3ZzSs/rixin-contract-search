from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.api.screening_tasks import load_owned_task
from app.db import get_session
from app.enums import AuditEventType, EvidenceSourceTool
from app.errors import ApiError
from app.models import ConditionVerdict, ScreeningDocumentResult
from app.schemas import QmdDocumentPreviewResponse, QmdEvidenceContextResponse
from app.services.audit import write_audit
from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, clean_optional_string, extract_text

router = APIRouter()


@router.get("/preview", response_model=QmdDocumentPreviewResponse)
def preview(task_id: UUID, document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = _load_owned_qmd_task(session, task_id, document_uri, auth)
    try:
        preview_payload = dict(QmdClient().document_preview(document_uri))
    except QmdUnavailable as exc:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404) from exc
    preview_payload["can_open"] = bool(preview_payload.get("can_open", False)) and _is_api_redirect_target(preview_payload.get("open_url"))
    preview_payload["can_download"] = bool(preview_payload.get("can_download", False)) and _is_api_redirect_target(preview_payload.get("download_url"))

    write_audit(
        session,
        AuditEventType.document_previewed.value,
        {
            "document_uri": document_uri,
            "task_id": str(task.id),
            "source_tool": "document_preview",
        },
        actor_id=auth.owner_id,
        task=task,
    )
    session.commit()
    return preview_payload


@router.get("/evidence-context", response_model=QmdEvidenceContextResponse)
def evidence_context(
    task_id: UUID,
    document_uri: str,
    page: int | None = None,
    condition_id: str | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
):
    task = _load_owned_qmd_task(session, task_id, document_uri, auth)
    try:
        payload = QmdClient().doc_read(document_uri, page=page, anchor=None, window=2)
    except QmdUnavailable as exc:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404) from exc

    context = _build_evidence_context(document_uri, payload, page=page, condition_id=condition_id)
    if context is None:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404)
    write_audit(
        session,
        AuditEventType.document_previewed.value,
        {
            "document_uri": document_uri,
            "task_id": str(task.id),
            "condition_id": context.condition_id,
            "page": context.page,
            "anchor": context.anchor,
            "source_tool": context.source_tool.value,
        },
        actor_id=auth.owner_id,
        task=task,
    )
    session.commit()
    return context


@router.get("/open-link")
def open_link(task_id: UUID, document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = _load_owned_qmd_task(session, task_id, document_uri, auth)
    preview = _load_preview(document_uri, error_code="qmd_preview_unavailable")
    open_url = preview.get("open_url")
    open_url = _safe_redirect_target(open_url, error_code="qmd_preview_unavailable")
    write_audit(
        session,
        AuditEventType.document_opened.value,
        {
            "document_uri": document_uri,
            "task_id": str(task.id),
            "source_tool": "open_link",
        },
        actor_id=auth.owner_id,
        task=task,
    )
    session.commit()
    return RedirectResponse(open_url, status_code=307)


@router.get("/download")
def download(task_id: UUID, document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    task = _load_owned_qmd_task(session, task_id, document_uri, auth)
    preview = _load_preview(document_uri, error_code="qmd_download_unavailable")
    download_url = preview.get("download_url")
    download_url = _safe_redirect_target(download_url, error_code="qmd_download_unavailable")
    write_audit(
        session,
        AuditEventType.document_downloaded.value,
        {
            "document_uri": document_uri,
            "task_id": str(task.id),
            "source_tool": "download",
        },
        actor_id=auth.owner_id,
        task=task,
    )
    session.commit()
    return RedirectResponse(download_url, status_code=307)


def _load_preview(document_uri: str, error_code: str) -> dict[str, Any]:
    try:
        return QmdClient().document_preview(document_uri)
    except QmdUnavailable as exc:
        raise ApiError(error_code, "QMD preview is unavailable", 404) from exc


def _load_owned_qmd_task(session: Session, task_id: UUID, document_uri: str, auth: AuthContext):
    task = load_owned_task(session, task_id, auth)
    if not _document_uri_is_associated(session, task.id, document_uri):
        raise ApiError("not_found", "Not found", 404)
    return task


def _document_uri_is_associated(session: Session, task_id: UUID, document_uri: str) -> bool:
    if session.scalar(
        select(ScreeningDocumentResult.id).where(
            ScreeningDocumentResult.task_id == task_id,
            ScreeningDocumentResult.document_uri == document_uri,
        )
    ) is not None:
        return True
    return (
        session.scalar(
            select(ConditionVerdict.id).where(
                ConditionVerdict.task_id == task_id,
                ConditionVerdict.document_uri == document_uri,
            )
        )
        is not None
    )


def _build_evidence_context(
    document_uri: str,
    payload: dict[str, Any],
    *,
    page: int | None,
    condition_id: str | None,
) -> QmdEvidenceContextResponse | None:
    structured = payload.get("structuredContent")
    structured = structured if isinstance(structured, dict) else {}
    text = clean_optional_string(structured.get("text")) or extract_text(payload)
    if not text:
        return None
    anchor = clean_optional_string(structured.get("anchor"))
    structured_condition_id = clean_optional_string(structured.get("condition_id"))
    caller_condition_id = clean_optional_string(condition_id)
    context_page = structured.get("page")
    if not isinstance(context_page, int):
        context_page = page
    source_tool = structured.get("source_tool")
    if not isinstance(source_tool, str) or source_tool not in {tool.value for tool in EvidenceSourceTool}:
        source_tool = EvidenceSourceTool.doc_read.value
    return QmdEvidenceContextResponse(
        document_uri=document_uri,
        condition_id=caller_condition_id or structured_condition_id,
        page=context_page,
        anchor=anchor,
        text=text,
        source_tool=EvidenceSourceTool(source_tool),
    )


def _safe_redirect_target(value: Any, *, error_code: str) -> str:
    target = clean_optional_string(value)
    if target is None:
        raise ApiError(error_code, "QMD preview is unavailable", 404)
    if not _is_safe_root_relative_target(target):
        raise ApiError(error_code, "QMD preview is unavailable", 404)
    return target


def _is_api_redirect_target(value: Any) -> bool:
    target = clean_optional_string(value)
    if target is None:
        return False
    return _is_safe_root_relative_target(target)


def _is_safe_root_relative_target(target: str) -> bool:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return False
    if not target.startswith("/") or target.startswith("//"):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in target):
        return False
    if "\\" in target:
        return False

    decoded_path = unquote(parsed.path)
    if "\\" in decoded_path:
        return False
    segments = decoded_path.split("/")
    if any(segment in {".", ".."} for segment in segments):
        return False
    return True
