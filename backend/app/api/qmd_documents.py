from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.db import get_session
from app.enums import AuditEventType, EvidenceSourceTool
from app.errors import ApiError
from app.schemas import QmdDocumentPreviewResponse, QmdEvidenceContextResponse
from app.services.audit import write_audit
from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, clean_optional_string, extract_text

router = APIRouter()


@router.get("/preview", response_model=QmdDocumentPreviewResponse)
def preview(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    try:
        preview_payload = QmdClient().document_preview(document_uri)
    except QmdUnavailable as exc:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404) from exc

    write_audit(
        session,
        AuditEventType.document_previewed.value,
        {
            "document_uri": document_uri,
            "document_title": preview_payload.get("document_title"),
            "collection": preview_payload.get("collection"),
            "can_open": preview_payload.get("can_open", False),
            "can_download": preview_payload.get("can_download", False),
        },
        actor_id=auth.owner_id,
    )
    session.commit()
    return preview_payload


@router.get("/evidence-context", response_model=QmdEvidenceContextResponse)
def evidence_context(
    document_uri: str,
    page: int | None = None,
    auth: AuthContext = Depends(get_auth),
    session: Session = Depends(get_session),
):
    try:
        payload = QmdClient().doc_read(document_uri, page=page, anchor=None, window=2)
    except QmdUnavailable as exc:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404) from exc

    context = _build_evidence_context(document_uri, payload, page=page)
    if context is None:
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404)
    write_audit(
        session,
        AuditEventType.document_previewed.value,
        {
            "document_uri": document_uri,
            "page": context.page,
            "anchor": context.anchor,
            "source_tool": context.source_tool.value,
        },
        actor_id=auth.owner_id,
    )
    session.commit()
    return context


@router.get("/open-link")
def open_link(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    preview = _load_preview(document_uri, error_code="qmd_preview_unavailable")
    open_url = preview.get("open_url")
    if not isinstance(open_url, str) or not open_url.strip():
        raise ApiError("qmd_preview_unavailable", "QMD preview is unavailable", 404)
    write_audit(session, AuditEventType.document_opened.value, {"document_uri": document_uri, "open_url": open_url}, actor_id=auth.owner_id)
    session.commit()
    return RedirectResponse(open_url, status_code=307)


@router.get("/download")
def download(document_uri: str, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    preview = _load_preview(document_uri, error_code="qmd_download_unavailable")
    download_url = preview.get("download_url")
    if not isinstance(download_url, str) or not download_url.strip():
        raise ApiError("qmd_download_unavailable", "QMD download is unavailable", 404)
    write_audit(session, AuditEventType.document_downloaded.value, {"document_uri": document_uri, "download_url": download_url}, actor_id=auth.owner_id)
    session.commit()
    return RedirectResponse(download_url, status_code=307)


def _load_preview(document_uri: str, error_code: str) -> dict[str, Any]:
    try:
        return QmdClient().document_preview(document_uri)
    except QmdUnavailable as exc:
        raise ApiError(error_code, "QMD preview is unavailable", 404) from exc


def _build_evidence_context(document_uri: str, payload: dict[str, Any], *, page: int | None) -> QmdEvidenceContextResponse | None:
    structured = payload.get("structuredContent")
    structured = structured if isinstance(structured, dict) else {}
    text = clean_optional_string(structured.get("text")) or extract_text(payload)
    if not text:
        return None
    anchor = clean_optional_string(structured.get("anchor"))
    condition_id = clean_optional_string(structured.get("condition_id"))
    context_page = structured.get("page")
    if not isinstance(context_page, int):
        context_page = page
    source_tool = structured.get("source_tool")
    if not isinstance(source_tool, str) or source_tool not in {tool.value for tool in EvidenceSourceTool}:
        source_tool = EvidenceSourceTool.doc_read.value
    return QmdEvidenceContextResponse(
        document_uri=document_uri,
        condition_id=condition_id,
        page=context_page,
        anchor=anchor,
        text=text,
        source_tool=EvidenceSourceTool(source_tool),
    )
