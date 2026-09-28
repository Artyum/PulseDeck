from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = _PROJECT_ROOT / "frontend" / "static"
_ASSET_DIRS = ("css", "js", "vendor")
_DIGEST_LEN = 5

_cached_signature: tuple[str, tuple[tuple[str, int, int], ...]] | None = None
_cached_digest: str | None = None


def clear_static_asset_version_cache() -> None:
    global _cached_signature, _cached_digest
    _cached_signature = None
    _cached_digest = None


def reset_static_asset_version_cache() -> None:
    clear_static_asset_version_cache()


def _version_prefix() -> str:
    from app.config import get_settings

    return (get_settings().static_asset_version or "").strip()


def _iter_asset_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for name in _ASSET_DIRS:
        directory = _STATIC_DIR / name
        if not directory.is_dir():
            continue
        for path in sorted(
            directory.rglob("*"), key=lambda p: p.relative_to(_STATIC_DIR).as_posix()
        ):
            if path.is_file():
                files.append((path.relative_to(_STATIC_DIR).as_posix(), path))
    return files


def _signature() -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for rel, path in _iter_asset_files():
        try:
            st = path.stat()
        except OSError:
            continue
        rows.append((rel, st.st_mtime_ns, st.st_size))
    return tuple(rows)


def _content_digest() -> str:
    files = _iter_asset_files()
    if not files:
        return "0"
    digest = hashlib.sha256()
    for rel, path in files:
        digest.update(rel.encode())
        digest.update(b"\0")
        with suppress(OSError):
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:_DIGEST_LEN]


def get_static_asset_version() -> str:
    global _cached_signature, _cached_digest
    prefix = _version_prefix()
    signature = (prefix, _signature())
    if _cached_signature != signature or _cached_digest is None:
        _cached_digest = _content_digest()
        _cached_signature = signature
    if prefix:
        return f"{prefix}-{_cached_digest}"
    return _cached_digest


def _normalize_static_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip().lstrip("/")
    cleaned = cleaned.removeprefix("static/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("invalid static path")
    return cleaned


def _resolved_static_file(cleaned: str) -> Path | None:
    static_root = _STATIC_DIR.resolve()
    target = (static_root / cleaned).resolve()
    try:
        target.relative_to(static_root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return target


def static_url(path: str) -> str:
    cleaned = _normalize_static_path(path)
    if _resolved_static_file(cleaned) is None:
        return f"/static/{cleaned}?v=0"
    return f"/static/{cleaned}?v={get_static_asset_version()}"
