from __future__ import annotations

import logging
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from markupsafe import Markup

logger = logging.getLogger("pulsedeck.app.utils.icons")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ICONS_DIR = _PROJECT_ROOT / "frontend" / "static" / "icons"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_ALIASES = {
    "attachments": "attach",
    "members": "people",
    "mine": "people",
    "view_all": "all",
    "open": "all",
    "waiting_on_me": "waiting_on_client",
}


@lru_cache(maxsize=256)
def _load_svg(name: str) -> str | None:
    path = (_ICONS_DIR / f"{name}.svg").resolve()
    if not path.is_relative_to(_ICONS_DIR.resolve()) or not path.is_file():
        return None
    return _COMMENT_RE.sub("", path.read_text(encoding="utf-8")).strip()


def _inner(raw: str) -> str:
    match = _SVG_OPEN_RE.search(raw)
    if not match:
        return ""
    rest = raw[match.end() :]
    close = rest.rfind("</svg>")
    if close == -1:
        return rest.strip()
    return rest[:close].strip()


def render_icon(name: str | None, class_name: str = "icon") -> Markup:
    if not name or not _NAME_RE.match(name):
        return Markup("")
    resolved = _ALIASES.get(name, name)
    raw = _load_svg(resolved)
    if raw is None:
        logger.warning("Nie znaleziono ikony SVG: %s", name)
        return Markup("")
    inner = _inner(raw)
    if not inner:
        logger.warning("Ikona SVG bez treści: %s", name)
        return Markup("")
    cls = escape(class_name or "icon", quote=True)
    return Markup(
        f'<svg class="{cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{inner}</svg>'
    )


icon = render_icon
