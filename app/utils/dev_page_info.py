from __future__ import annotations

import inspect
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import Request
from jinja2 import Environment, meta

from app.config import project_root

logger = logging.getLogger("pulsedeck.app")

_TEMPLATES_PREFIX = "frontend/templates"
_DEV_SKIP_TEMPLATE_REFS = frozenset(
    {
        "base.html",
        "base_app.html",
        "admin/base_admin.html",
        "admin/base_settings.html",
        "auth/base_profile.html",
        "partials/dev_panel.html",
        "partials/icons.html",
    }
)
_DEV_API_RE = re.compile(r"/api/[A-Za-z0-9_./-]*[A-Za-z0-9_-]")
_DEV_JS_RE = re.compile(r"static_url\(\s*['\"]js/([^'\"]+)['\"]")
_COPY_KEYS = ("url", "template", "partials", "api", "js", "route", "file")


def _template_source(env: Environment, template_name: str) -> str:
    loader = env.loader
    if loader is None:
        return ""
    try:
        return loader.get_source(env, template_name)[0]
    except Exception:
        logger.debug("Nie udało się odczytać szablonu %s", template_name, exc_info=True)
        return ""


def _template_refs(env: Environment, template_name: str) -> list[str]:
    source = _template_source(env, template_name)
    if not source:
        return []
    try:
        refs = [ref for ref in meta.find_referenced_templates(env.parse(source)) if ref]
    except Exception:
        logger.debug(
            "Nie udało się odczytać referencji szablonu %s",
            template_name,
            exc_info=True,
        )
        return []
    return [ref for ref in refs if ref not in _DEV_SKIP_TEMPLATE_REFS]


def _scan_page_assets(env: Environment, template_name: str) -> tuple[str, str, str]:
    names = [template_name, *_template_refs(env, template_name)]
    apis: set[str] = set()
    scripts: set[str] = set()
    sources: dict[str, str] = {}
    for name in names:
        sources[name] = _template_source(env, name)
        for match in _DEV_API_RE.finditer(sources[name]):
            apis.add(match.group(0).rstrip("/"))
    for match in _DEV_JS_RE.finditer(sources.get(template_name, "")):
        path = match.group(1)
        if not path.startswith("vendor/"):
            scripts.add(f"frontend/static/js/{path}")
    partials = [f"{_TEMPLATES_PREFIX}/{ref}" for ref in names[1:]]
    return (
        ", ".join(sorted(set(partials))),
        ", ".join(sorted(apis)),
        ", ".join(sorted(scripts)),
    )


def _handler_location(endpoint: Any) -> str:
    if endpoint is None:
        return ""
    try:
        src = inspect.getsourcefile(endpoint) or inspect.getfile(endpoint)
        rel = Path(src).resolve().relative_to(project_root())
        lineno = inspect.getsourcelines(endpoint)[1]
        return f"{rel.as_posix()}:{lineno}"
    except Exception:
        logger.debug("Nie udało się ustalić pliku handlera strony", exc_info=True)
        return ""


def _copy_text(info: dict[str, str]) -> str:
    lines = []
    for key in _COPY_KEYS:
        value = info.get(key) or ""
        if value:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def build_dev_page_info(
    request: Request, env: Environment, template_name: str
) -> dict[str, str]:
    route = request.scope.get("route")
    route_path = str(getattr(route, "path", "") or "") if route is not None else ""
    actual_path = request.url.path
    partials, apis, extra_js = _scan_page_assets(env, template_name)
    info = {
        "url": str(request.url),
        "template": f"{_TEMPLATES_PREFIX}/{template_name}",
        "partials": partials,
        "api": apis,
        "js": extra_js,
        "file": _handler_location(request.scope.get("endpoint")),
    }
    if route_path and route_path != actual_path:
        info["route"] = route_path
    info["copy_text"] = _copy_text(info)
    return info
