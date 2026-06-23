from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, get_auth
from app.db import get_session
from app.enums import AuditEventType
from app.errors import ApiError
from app.models import ContractFile
from app.services.audit import write_audit
from app.services.storage import ensure_under_storage

router = APIRouter()


@router.get("/{contract_id}/download")
def download_contract(contract_id: UUID, auth: AuthContext = Depends(get_auth), session: Session = Depends(get_session)):
    contract = session.get(ContractFile, contract_id)
    if contract is None:
        raise ApiError("not_found", "Not found", 404)
    if contract.owner_id != auth.owner_id:
        write_audit(session, AuditEventType.permission_denied.value, {"resource_type": "contract_file", "resource_id": str(contract_id), "reason": "owner_mismatch"}, actor_id=auth.owner_id, task_id=contract.task_id, contract_id=contract.id)
        session.commit()
        raise ApiError("not_found", "Not found", 404)
    path = ensure_under_storage(Path(contract.stored_path))
    if not path.exists():
        raise ApiError("download_file_missing", "Download file is missing", 404)
    if not path.is_file():
        raise ApiError("download_file_unreadable", "Download file is unreadable", 404)
    write_audit(session, AuditEventType.download.value, {"task_id": str(contract.task_id), "contract_id": str(contract.id), "file_name": contract.original_filename}, actor_id=auth.owner_id, task_id=contract.task_id, contract_id=contract.id)
    session.commit()
    return FileResponse(path, filename=contract.original_filename, media_type=contract.content_type)
