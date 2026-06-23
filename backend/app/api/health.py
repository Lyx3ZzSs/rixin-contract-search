from typing import Any

from fastapi import APIRouter

from app.config import redact_url, sanitize_secrets, settings
from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable

router = APIRouter()


@router.get("/runtime/status")
def runtime_status() -> dict[str, object]:
    return settings.redacted_runtime_status()


@router.get("/qmd/status")
def qmd_status() -> dict[str, object]:
    expected = [item.strip() for item in settings.QMD_COLLECTIONS.split(",") if item.strip()]
    unavailable_collections = [{"name": name, "exists": False, "document_count": None} for name in expected]
    try:
        status = QmdClient().status()
    except QmdUnavailable as exc:
        return {
            "available": False,
            "error": {"type": "qmd_unavailable", "message": redact_qmd_error_message(exc)},
            "collections": unavailable_collections,
            "configured_collections": unavailable_collections,
        }
    except Exception as exc:
        return {
            "available": False,
            "error": {"type": "qmd_status_error", "message": redact_qmd_error_message(exc)},
            "collections": unavailable_collections,
            "configured_collections": unavailable_collections,
        }

    available = indexed_collections(status)
    collections = [
        {
            "name": name,
            "exists": name in available,
            "document_count": available.get(name),
        }
        for name in expected
    ]
    return {
        "available": True,
        "backend": settings.QMD_BACKEND,
        "url": redact_url(settings.QMD_MCP_URL),
        "collections": collections,
        "configured_collections": collections,
        "upstream_status": sanitize_secrets(status),
    }


def indexed_collections(status: dict[str, Any]) -> dict[str, int | None]:
    collections = status.get("collections", [])
    indexed: dict[str, int | None] = {}
    if not isinstance(collections, list):
        return indexed
    for item in collections:
        if isinstance(item, str):
            indexed[item] = None
            continue
        if not isinstance(item, dict) or not item.get("name"):
            continue
        indexed[str(item["name"])] = collection_document_count(item)
    return indexed


def redact_qmd_error_message(exc: Exception) -> str:
    if len(exc.args) == 1:
        return str(sanitize_secrets(exc.args[0]))
    if exc.args:
        return str(sanitize_secrets(exc.args))
    return sanitize_secrets(str(exc))


def collection_document_count(collection: dict[str, Any]) -> int | None:
    for key in ("document_count", "count", "documents", "doc_count", "files"):
        value = collection.get(key)
        if isinstance(value, int):
            return value
    return None
