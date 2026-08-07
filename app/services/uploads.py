from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import uuid
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import resolve_upload_dir
from app.models.ticket import Attachment, Comment
from app.models.user import User
from app.services import projects as project_service
from app.services import tickets as ticket_service
from app.services.portal_settings import get_portal_settings
from app.utils.i18n import DEFAULT_LANG, t

logger = logging.getLogger("pulsedeck.app.uploads")

ALLOWED_IMAGE = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
ALLOWED_EXTENSIONS = ALLOWED_IMAGE | frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".txt",
        ".csv",
        ".log",
        ".json",
        ".xml",
        ".zip",
        ".rar",
        ".7z",
    }
)
_PLAIN_TEXT = frozenset({".txt", ".csv", ".log"})
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_MAGIC = {
    ".pdf": (b"%PDF",),
    ".zip": _ZIP_MAGIC,
    ".docx": _ZIP_MAGIC,
    ".xlsx": _ZIP_MAGIC,
    ".pptx": _ZIP_MAGIC,
    ".rar": (b"Rar!\x1a\x07",),
    ".7z": (b"7z\xbc\xaf\x27\x1c",),
}
JPEG_QUALITY = 90
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 4000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def sanitize_original_filename(filename: str | None) -> str:
    if not filename:
        return "plik"
    normalized = filename.replace("\\", "/")
    base = PurePosixPath(normalized).name.strip()
    if not base or base in (".", ".."):
        return "plik"
    return base[:255]


def _ext(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def _limit_mb(n: int) -> int:
    return max(1, (n + 1024 * 1024 - 1) // (1024 * 1024))


def _bad(lang: str, key: str, **kwargs: object) -> HTTPException:
    return HTTPException(
        status_code=400, detail=t(lang, f"messages.uploads.{key}", **kwargs)
    )


def _require_utf8(data: bytes, *, lang: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _bad(lang, "invalid_file") from exc


def _validate_non_image(ext: str, data: bytes, *, lang: str) -> None:
    magic = _MAGIC.get(ext)
    if magic is not None:
        if not data.startswith(magic):
            raise _bad(lang, "invalid_file")
        return

    if ext in _PLAIN_TEXT:
        _require_utf8(data, lang=lang)
        return

    if ext == ".json":
        try:
            json.loads(_require_utf8(data, lang=lang))
        except json.JSONDecodeError as exc:
            raise _bad(lang, "invalid_file") from exc
        return

    if ext == ".xml":
        if not _require_utf8(data, lang=lang).lstrip().startswith("<"):
            raise _bad(lang, "invalid_file")
        return

    raise _bad(lang, "formats")


def _save_image(
    data: bytes,
    *,
    target_dir: Path,
    subdir: str,
    file_id: str,
    digest: str,
    lang: str,
) -> str:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise _bad(lang, "invalid_image") from exc
    width, height = img.size
    if width * height > MAX_IMAGE_PIXELS or max(width, height) > MAX_IMAGE_DIMENSION:
        raise _bad(lang, "image_too_large")
    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(
            img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
        )
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    stored_name = f"{file_id}_{digest}.jpg"
    img.save(
        target_dir / stored_name, format="JPEG", quality=JPEG_QUALITY, optimize=True
    )
    return f"{subdir}/{stored_name}"


async def save_upload(
    file: UploadFile,
    *,
    subdir: str = "tickets",
    lang: str | None = None,
    db: Session | None = None,
) -> tuple[str, str]:
    lang = lang or DEFAULT_LANG
    portal = get_portal_settings(db)
    original = sanitize_original_filename(file.filename)
    ext = _ext(original)
    data = await file.read()
    if not data:
        raise _bad(lang, "empty")
    if ext not in ALLOWED_EXTENSIONS:
        raise _bad(lang, "formats")

    is_image = ext in ALLOWED_IMAGE
    max_bytes = (
        portal.upload_max_image_bytes if is_image else portal.upload_max_file_bytes
    )
    if len(data) > max_bytes:
        raise _bad(
            lang,
            "too_large_image" if is_image else "too_large_file",
            mb=_limit_mb(max_bytes),
        )

    target_dir = resolve_upload_dir() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:12]
    file_id = uuid.uuid4().hex[:10]

    if is_image:
        return original, _save_image(
            data,
            target_dir=target_dir,
            subdir=subdir,
            file_id=file_id,
            digest=digest,
            lang=lang,
        )

    _validate_non_image(ext, data, lang=lang)
    stored_name = f"{file_id}_{digest}{ext}"
    (target_dir / stored_name).write_bytes(data)
    return original, f"{subdir}/{stored_name}"


def resolve_safe_upload_path(rel_path: str) -> Path | None:
    if not rel_path or ".." in PurePosixPath(rel_path).parts:
        return None
    root = resolve_upload_dir().resolve()
    try:
        full = (root / rel_path).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        full.relative_to(root)
    except ValueError:
        return None
    if not full.is_file():
        return None
    return full


def get_attachment_for_download(
    db: Session,
    attachment_id: int,
    user: User,
    *,
    lang: str | None = None,
) -> Attachment:
    lang = lang or DEFAULT_LANG
    att = db.scalar(
        select(Attachment)
        .where(Attachment.id == attachment_id)
        .options(
            joinedload(Attachment.ticket),
            joinedload(Attachment.comment).joinedload(Comment.ticket),
        )
    )
    if not att:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))

    ticket = att.ticket
    comment: Comment | None = att.comment
    if comment is not None:
        ticket = comment.ticket
        if ticket is None:
            raise HTTPException(
                status_code=404, detail=t(lang, "messages.http.not_found")
            )
        if comment.is_internal and not project_service.has_staff_capabilities(
            db, ticket.project_id, user
        ):
            raise HTTPException(
                status_code=404, detail=t(lang, "messages.http.not_found")
            )
    if ticket is None:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))

    if not ticket_service.can_view_ticket(db, user, ticket):
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))
    return att


def file_response_for_attachment(
    att: Attachment, *, lang: str | None = None
) -> FileResponse:
    lang = lang or DEFAULT_LANG
    path = resolve_safe_upload_path(att.file_path)
    if path is None:
        logger.warning("Attachment file missing or unsafe path id=%s", att.id)
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))
    ext = path.suffix.lower()
    media_type, _ = mimetypes.guess_type(str(path))
    if not media_type:
        media_type = "application/octet-stream"
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=att.file_name,
        content_disposition_type="inline" if ext in ALLOWED_IMAGE else "attachment",
    )
