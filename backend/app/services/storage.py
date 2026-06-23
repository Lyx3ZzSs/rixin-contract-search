import os
import shutil
from pathlib import Path
from uuid import UUID

from app.config import settings
from app.errors import ApiError


def storage_root() -> Path:
    root = Path(settings.STORAGE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_under_storage(path: Path) -> Path:
    root = storage_root().resolve()
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ApiError("storage_path_escape", "Invalid storage path", 500)
    return resolved


def task_dir(task_id: UUID) -> Path:
    path = storage_root() / "tasks" / str(task_id)
    path.mkdir(parents=True, exist_ok=True)
    return ensure_under_storage(path)


def uploads_dir(task_id: UUID) -> Path:
    path = task_dir(task_id) / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return ensure_under_storage(path)


def parsed_dir(task_id: UUID) -> Path:
    path = task_dir(task_id) / "parsed"
    path.mkdir(parents=True, exist_ok=True)
    return ensure_under_storage(path)


def qmd_docs_dir(task_id: UUID) -> Path:
    path = task_dir(task_id) / "qmd_docs"
    path.mkdir(parents=True, exist_ok=True)
    return ensure_under_storage(path)


def atomic_move(src: Path, dest: Path) -> None:
    ensure_under_storage(src)
    ensure_under_storage(dest.parent)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)


def remove_path(path: Path) -> None:
    try:
        resolved = ensure_under_storage(path)
    except ApiError:
        return
    if resolved.is_dir():
        shutil.rmtree(resolved, ignore_errors=True)
    elif resolved.exists():
        resolved.unlink(missing_ok=True)

