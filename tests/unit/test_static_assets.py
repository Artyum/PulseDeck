from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

import pytest

from app.utils import static_assets
from app.utils.static_assets import get_static_asset_version, static_url

_HEX_5 = re.compile(r"^[0-9a-f]{5}$")


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setattr(static_assets, "_version_prefix", lambda: "")
    static_assets.clear_static_asset_version_cache()
    yield
    static_assets.clear_static_asset_version_cache()


def _bind_tmp_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    static = tmp_path / "frontend" / "static"
    (static / "css").mkdir(parents=True)
    (static / "js").mkdir(parents=True)
    monkeypatch.setattr(static_assets, "_STATIC_DIR", static)
    static_assets.clear_static_asset_version_cache()
    return static


def test_static_url_appends_shared_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = _bind_tmp_static(tmp_path, monkeypatch)
    (static / "css" / "app.css").write_text("body{}", encoding="utf-8")
    (static / "js" / "app.js").write_text("console.log(1)", encoding="utf-8")
    version = get_static_asset_version()
    assert _HEX_5.fullmatch(version)
    assert static_url("js/app.js") == f"/static/js/app.js?v={version}"
    assert static_url("/static/css/app.css") == f"/static/css/app.css?v={version}"
    assert static_url("static/js/app.js") == f"/static/js/app.js?v={version}"


def test_static_url_missing_file_uses_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_tmp_static(tmp_path, monkeypatch)
    assert static_url("css/nope.css") == "/static/css/nope.css?v=0"


def test_static_url_rejects_parent_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_tmp_static(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="invalid static path"):
        static_url("../secret")


def test_fingerprint_changes_when_file_content_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = _bind_tmp_static(tmp_path, monkeypatch)
    (static / "css" / "app.css").write_text("AAAAA", encoding="utf-8")
    (static / "js" / "app.js").write_text("xxxxx", encoding="utf-8")
    before = get_static_asset_version()
    (static / "css" / "app.css").write_text("BBBBB!", encoding="utf-8")
    after = get_static_asset_version()
    assert before != after
    assert _HEX_5.fullmatch(after)


def test_fingerprint_empty_dirs_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_tmp_static(tmp_path, monkeypatch)
    assert get_static_asset_version() == "0"


def test_fingerprint_prefix_from_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = _bind_tmp_static(tmp_path, monkeypatch)
    (static / "css" / "app.css").write_text("body{}", encoding="utf-8")
    monkeypatch.setattr(static_assets, "_version_prefix", lambda: "deploy1")
    version = get_static_asset_version()
    assert version.startswith("deploy1-")
    assert _HEX_5.fullmatch(version.removeprefix("deploy1-"))
