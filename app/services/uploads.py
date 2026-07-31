from __future__ import annotations

import hashlib
import io
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
from app.services import tickets as ticket_service
from app.utils.i18n import DEFAULT_LANG, t

logger = logging.getLogger("pulsedeck.app.uploads")

ALLOWED_IMAGE = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
ALLOWED_PDF = frozenset({".pdf"})
MAX_BYTES = 5 * 1024 * 1024
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


async def save_upload(
    file: UploadFile,
    *,
    subdir: str = "tickets",
    lang: str | None = None,
) -> tuple[str, str]:
    lang = lang or DEFAULT_LANG
    original = sanitize_original_filename(file.filename)
    ext = _ext(original)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail=t(lang, "messages.uploads.empty"))
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=400, detail=t(lang, "messages.uploads.too_large")
        )

    upload_root = resolve_upload_dir()
    target_dir = upload_root / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:12]
    file_id = uuid.uuid4().hex[:10]

    if ext in ALLOWED_IMAGE:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=t(lang, "messages.uploads.invalid_image")
            ) from exc
        width, height = img.size
        if (
            width * height > MAX_IMAGE_PIXELS
            or max(width, height) > MAX_IMAGE_DIMENSION
        ):
            raise HTTPException(
                status_code=400, detail=t(lang, "messages.uploads.image_too_large")
            )
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
        out_path = target_dir / stored_name
        img.save(out_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        rel = f"{subdir}/{stored_name}"
        return original, rel

    if ext in ALLOWED_PDF:
        if not data.startswith(b"%PDF"):
            raise HTTPException(
                status_code=400, detail=t(lang, "messages.uploads.invalid_pdf")
            )
        stored_name = f"{file_id}_{digest}.pdf"
        out_path = target_dir / stored_name
        out_path.write_bytes(data)
        return original, f"{subdir}/{stored_name}"

    raise HTTPException(
        status_code=400,
        detail=t(lang, "messages.uploads.formats"),
    )


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
        if comment.is_internal and not user.is_staff:
            raise HTTPException(
                status_code=404, detail=t(lang, "messages.http.not_found")
            )
        ticket = comment.ticket
    if ticket is None:
        raise HTTPException(status_code=404, detail=t(lang, "messages.http.not_found"))

    ticket_service.require_project_access(db, user, ticket.project_id, lang=lang)
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
    disposition = "inline" if ext in ALLOWED_IMAGE else "attachment"
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=att.file_name,
        content_disposition_type=disposition,
    )
