import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from app.config import settings
from app.errors import ApiError
from app.services.storage import atomic_move, remove_path, uploads_dir

CHUNK_SIZE = 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass
class StoredUpload:
    original_filename: str
    stored_path: Path
    content_type: str
    sha256: str
    file_size_bytes: int
    page_count: int | None


def sanitize_filename(filename: str) -> str:
    base = Path(filename or "").name.strip()
    if not base:
        raise ApiError("unsupported_file_type", "Unsupported file type", 400)
    stem = Path(base).stem
    ext = Path(base).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", stem).strip("._") or "file"
    if ext not in ALLOWED_EXTENSIONS:
        raise ApiError("unsupported_file_type", "Unsupported file type", 400, {"filename": base})
    max_stem = max(1, 180 - len(ext))
    return f"{stem[:max_stem]}{ext}"


def dedupe_filename(filename: str, used: set[str]) -> str:
    if filename not in used:
        used.add(filename)
        return filename
    path = Path(filename)
    stem, ext = path.stem, path.suffix
    idx = 2
    while True:
        suffix = f"_{idx}"
        candidate = f"{stem[: max(1, 180 - len(ext) - len(suffix))]}{suffix}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        idx += 1


async def store_uploads(task_id: UUID, files: list[UploadFile]) -> list[StoredUpload]:
    if not files:
        raise ApiError("file_required", "At least one file is required", 400)
    if len(files) > settings.MAX_FILES_PER_TASK:
        raise ApiError("too_many_files", "Too many files", 400, {"limit": settings.MAX_FILES_PER_TASK})
    used: set[str] = set()
    stored: list[StoredUpload] = []
    try:
        for file in files:
            safe_name = dedupe_filename(sanitize_filename(file.filename or ""), used)
            stored.append(await store_single_upload(task_id, file, safe_name))
    except Exception:
        for item in stored:
            remove_path(item.stored_path)
        raise
    return stored


async def store_single_upload(task_id: UUID, file: UploadFile, safe_name: str) -> StoredUpload:
    ext = Path(safe_name).suffix.lower()
    expected_mime = EXT_TO_MIME[ext]
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    digest = hashlib.sha256()
    total = 0
    upload_dir = uploads_dir(task_id)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=upload_dir) as tmp:
            tmp_path = Path(tmp.name)
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ApiError("file_too_large", "File is too large", 400, {"limit": limit, "filename": safe_name})
                digest.update(chunk)
                tmp.write(chunk)
        if total == 0:
            raise ApiError("file_empty", "File is empty", 400, {"filename": safe_name})

        page_count = validate_content(tmp_path, ext, safe_name)
        final_path = upload_dir / f"{safe_name}"
        atomic_move(tmp_path, final_path)
        return StoredUpload(safe_name, final_path, expected_mime, digest.hexdigest(), total, page_count)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def validate_content(path: Path, ext: str, filename: str) -> int | None:
    if ext == ".pdf":
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ApiError("invalid_file_content", "Invalid file content", 400, {"filename": filename})
        try:
            reader = PdfReader(str(path))
            count = len(reader.pages)
        except Exception as exc:
            raise ApiError("invalid_file_content", "Invalid file content", 400, {"filename": filename}) from exc
        if count > settings.MAX_PAGES_PER_FILE:
            raise ApiError("too_many_pages", "Too many pages", 400, {"limit": settings.MAX_PAGES_PER_FILE})
        return count

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            fmt = (image.format or "").lower()
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ApiError("invalid_file_content", "Invalid file content", 400, {"filename": filename}) from exc
    if ext == ".png" and fmt != "png":
        raise ApiError("invalid_file_content", "Invalid file content", 400, {"filename": filename})
    if ext in {".jpg", ".jpeg"} and fmt != "jpeg":
        raise ApiError("invalid_file_content", "Invalid file content", 400, {"filename": filename})
    if width > 10000 or height > 10000 or width * height > 50_000_000:
        raise ApiError("image_too_large", "Image is too large", 400, {"filename": filename})
    return 1
