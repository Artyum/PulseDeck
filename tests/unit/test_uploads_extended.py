import asyncio
import io
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.config import get_settings, resolve_upload_dir
from app.services import tickets as ticket_service
from app.services.uploads import (
    file_response_for_attachment,
    get_attachment_for_download,
    resolve_safe_upload_path,
    save_upload,
)
from tests.helpers import make_ticket


def _png_bytes(size=(40, 40), mode="RGB", color=(10, 20, 30)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def _upload(filename: str, data: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def _save(file: UploadFile, **kwargs):
    return asyncio.run(save_upload(file, **kwargs))


@pytest.fixture()
def upload_tmp(tmp_path, monkeypatch, db_session):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield tmp_path / "uploads"
    get_settings.cache_clear()


class TestSaveUpload:
    def test_save_image_jpeg(self, upload_tmp):
        original, rel = _save(_upload("photo.png", _png_bytes()))
        assert original == "photo.png"
        assert rel.startswith("tickets/")
        assert rel.endswith(".jpg")
        assert (resolve_upload_dir() / rel).is_file()

    def test_save_rgba_image(self, upload_tmp):
        data = _png_bytes(mode="RGBA", color=(10, 20, 30, 128))
        original, rel = _save(_upload("alpha.png", data))
        assert original == "alpha.png"
        assert (resolve_upload_dir() / rel).is_file()

    def test_save_pdf(self, upload_tmp):
        data = b"%PDF-1.4 fake content"
        original, rel = _save(_upload("doc.pdf", data))
        assert original == "doc.pdf"
        assert rel.endswith(".pdf")
        assert (resolve_upload_dir() / rel).read_bytes() == data

    def test_save_zip(self, upload_tmp):
        data = b"PK\x03\x04" + b"zip-payload"
        original, rel = _save(_upload("pack.zip", data))
        assert original == "pack.zip"
        assert rel.endswith(".zip")
        assert (resolve_upload_dir() / rel).read_bytes() == data

    def test_save_docx(self, upload_tmp):
        data = b"PK\x03\x04" + b"docx-payload"
        original, rel = _save(_upload("note.docx", data))
        assert original == "note.docx"
        assert rel.endswith(".docx")

    def test_save_rar(self, upload_tmp):
        data = b"Rar!\x1a\x07\x00" + b"rar-payload"
        original, rel = _save(_upload("pack.rar", data))
        assert original == "pack.rar"
        assert rel.endswith(".rar")

    def test_save_7z(self, upload_tmp):
        data = b"7z\xbc\xaf\x27\x1c" + b"seven-payload"
        original, rel = _save(_upload("pack.7z", data))
        assert original == "pack.7z"
        assert rel.endswith(".7z")

    def test_save_txt(self, upload_tmp):
        data = "hello łódź\n".encode()
        original, rel = _save(_upload("note.txt", data))
        assert original == "note.txt"
        assert (resolve_upload_dir() / rel).read_bytes() == data

    def test_save_json(self, upload_tmp):
        data = b'{"ok": true, "n": 1}'
        original, rel = _save(_upload("data.json", data))
        assert original == "data.json"
        assert (resolve_upload_dir() / rel).read_bytes() == data

    def test_save_xml(self, upload_tmp):
        data = b'<?xml version="1.0"?><root/>'
        original, rel = _save(_upload("data.xml", data))
        assert original == "data.xml"
        assert (resolve_upload_dir() / rel).read_bytes() == data

    def test_empty_file_rejected(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("empty.png", b""))
        assert exc.value.status_code == 400

    def test_too_large_image_rejected(self, upload_tmp, db_session, monkeypatch):
        from dataclasses import replace

        from app.services import uploads as uploads_service
        from app.services.portal_settings import get_portal_settings

        portal = replace(get_portal_settings(db_session), upload_max_image_bytes=10)
        monkeypatch.setattr(
            uploads_service, "get_portal_settings", lambda _db=None: portal
        )
        with pytest.raises(HTTPException) as exc:
            _save(_upload("big.png", _png_bytes()))
        assert exc.value.status_code == 400

    def test_too_large_file_rejected(self, upload_tmp, db_session, monkeypatch):
        from dataclasses import replace

        from app.services import uploads as uploads_service
        from app.services.portal_settings import get_portal_settings

        portal = replace(get_portal_settings(db_session), upload_max_file_bytes=10)
        monkeypatch.setattr(
            uploads_service, "get_portal_settings", lambda _db=None: portal
        )
        with pytest.raises(HTTPException) as exc:
            _save(_upload("big.txt", b"hello world text"))
        assert exc.value.status_code == 400

    def test_invalid_image_rejected(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("bad.png", b"not-an-image"))
        assert exc.value.status_code == 400

    def test_invalid_pdf_rejected(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("bad.pdf", b"not-a-pdf"))
        assert exc.value.status_code == 400

    def test_fake_zip_rejected(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("evil.zip", b"MZ\x90\x00fake-exe"))
        assert exc.value.status_code == 400

    def test_invalid_json_rejected(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("bad.json", b"{not-json"))
        assert exc.value.status_code == 400

    def test_unsupported_format(self, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            _save(_upload("note.exe", b"MZ\x90\x00"))
        assert exc.value.status_code == 400

    def test_image_too_large_dimensions(self, upload_tmp, monkeypatch):
        monkeypatch.setattr("app.services.uploads.MAX_IMAGE_DIMENSION", 10)
        with pytest.raises(HTTPException) as exc:
            _save(_upload("big.png", _png_bytes(size=(20, 20))))
        assert exc.value.status_code == 400


class TestResolveSafeUploadPath:
    def test_empty(self, upload_tmp):
        assert resolve_safe_upload_path("") is None

    def test_traversal(self, upload_tmp):
        assert resolve_safe_upload_path("../secret.txt") is None

    def test_missing_file(self, upload_tmp):
        assert resolve_safe_upload_path("tickets/missing.jpg") is None

    def test_valid_file(self, upload_tmp):
        root = resolve_upload_dir()
        path = root / "tickets"
        path.mkdir(parents=True, exist_ok=True)
        target = path / "ok.jpg"
        target.write_bytes(b"x")
        resolved = resolve_safe_upload_path("tickets/ok.jpg")
        assert resolved == target.resolve()


class TestAttachmentDownload:
    def test_get_attachment_and_response(
        self, db_session, project_with_members, client_user, upload_tmp
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="With file"
        )
        root = resolve_upload_dir()
        rel = Path("tickets") / "att.jpg"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"jpeg-bytes")
        att = ticket_service.add_attachment(
            db_session,
            file_name="att.jpg",
            file_path=str(rel).replace("\\", "/"),
            ticket_id=ticket.id,
        )
        loaded = get_attachment_for_download(db_session, att.id, client_user)
        assert loaded.id == att.id
        response = file_response_for_attachment(loaded)
        assert response.status_code == 200
        assert response.filename == "att.jpg"
        assert "inline" in response.headers.get("content-disposition", "").lower()

    def test_non_image_attachment_disposition(
        self, db_session, project_with_members, client_user, upload_tmp
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="With json"
        )
        root = resolve_upload_dir()
        rel = Path("tickets") / "data.json"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b'{"a":1}')
        att = ticket_service.add_attachment(
            db_session,
            file_name="data.json",
            file_path=str(rel).replace("\\", "/"),
            ticket_id=ticket.id,
        )
        response = file_response_for_attachment(att)
        assert "attachment" in response.headers.get("content-disposition", "").lower()

    def test_attachment_not_found(self, db_session, client_user, upload_tmp):
        with pytest.raises(HTTPException) as exc:
            get_attachment_for_download(db_session, 99999, client_user)
        assert exc.value.status_code == 404

    def test_missing_file_response(
        self, db_session, project_with_members, client_user, upload_tmp
    ):
        ticket = make_ticket(
            db_session, project_with_members, client_user, title="Missing file"
        )
        att = ticket_service.add_attachment(
            db_session,
            file_name="gone.jpg",
            file_path="tickets/gone.jpg",
            ticket_id=ticket.id,
        )
        with pytest.raises(HTTPException) as exc:
            file_response_for_attachment(att)
        assert exc.value.status_code == 404
