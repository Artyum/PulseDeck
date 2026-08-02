from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import project_root

_ASSET_DIRS = ("css", "js", "vendor")
_version: str | None = None
_mtime_key: float | None = None


def _asset_files() -> tuple[float, list[tuple[str, Path]]]:
    root = project_root() / "frontend" / "static"
    files: list[tuple[str, Path]] = []
    mtime = 0.0
    for name in _ASSET_DIRS:
        directory = root / name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            try:
                mtime = max(mtime, path.stat().st_mtime)
            except OSError:
                continue
            files.append((path.relative_to(root).as_posix(), path))
    return mtime, files


def get_static_asset_version() -> str:
    global _version, _mtime_key
    mtime, files = _asset_files()
    if _version is not None and _mtime_key == mtime:
        return _version
    digest = hashlib.sha256()
    for rel, path in files:
        digest.update(rel.encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            pass
        digest.update(b"\0")
    _mtime_key = mtime
    _version = digest.hexdigest()[:12]
    return _version


def clear_static_asset_version_cache() -> None:
    global _version, _mtime_key
    _version = None
    _mtime_key = None


def static_url(path: str) -> str:
    cleaned = path.replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("invalid static path")
    return f"/static/{cleaned}?v={get_static_asset_version()}"
