from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile
from PIL import Image

from app.config import resolve_upload_dir
from app.utils.i18n import DEFAULT_LANG, t

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
