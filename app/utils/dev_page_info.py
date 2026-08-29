from __future__ import annotations

import inspect
import logging
from collections import deque
from typing import Any

from fastapi import Request
from jinja2 import Environment, nodes

logger = logging.getLogger("pulsedeck.app")

_TEMPLATES_PREFIX = "frontend/templates"


def _rel_template_path(name: str) -> str:
    return f"{_TEMPLATES_PREFIX}/{name}".replace("\\", "/")


def _const_template_name(node: nodes.Node | None) -> str | None:
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        return node.value
    return None


def _parse_template(env: Environment, name: str) -> tuple[str | None, list[str]]:
    try:
        source, _, _ = env.loader.get_source(env, name)  # type: ignore[union-attr]
    except Exception:
        logger.exception("Dev page info: cannot load template %s", name)
        return None, []
    try:
        ast = env.parse(source)
    except Exception:
        logger.exception("Dev page info: cannot parse template %s", name)
        return None, []

    extends: str | None = None
    for node in ast.find_all(nodes.Extends):
        extends = _const_template_name(node.template)
        if extends:
            break

    refs: list[str] = []
    for node in ast.find_all((nodes.Include, nodes.Import, nodes.FromImport)):
        ref = _const_template_name(node.template)
        if ref:
            refs.append(ref)
    return extends, refs


def _collect_partials(env: Environment, template_name: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    queue: deque[str] = deque([template_name])

    while queue:
        current = queue.popleft()
        _, refs = _parse_template(env, current)
        for ref in refs:
            if ref in seen or ref == template_name:
                continue
            seen.add(ref)
            ordered.append(_rel_template_path(ref))
            queue.append(ref)
    return ordered


def _route_meta(request: Request) -> tuple[str, str, str, str]:
    endpoint = request.scope.get("endpoint")
    handler_qid = ""
    handler_module = ""
    if endpoint is not None and callable(endpoint):
        fn = inspect.unwrap(endpoint)
        handler_module = getattr(fn, "__module__", "") or ""
        name = getattr(fn, "__name__", "") or ""
        if handler_module and name:
            handler_qid = f"{handler_module}.{name}"
        elif name:
            handler_qid = name

    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path
    method = request.method.upper()
    return handler_qid, handler_module, method, str(route_path)


def build_dev_page_info(
    request: Request,
    env: Environment,
    template_name: str,
    context_keys: list[str],
) -> dict[str, Any]:
    handler_qid, handler_module, method, route_path = _route_meta(request)
    extends_name, _ = _parse_template(env, template_name)
    return {
        "handler_qid": handler_qid,
        "handler_module": handler_module,
        "method": method,
        "route_path": route_path,
        "template": _rel_template_path(template_name),
        "extends": _rel_template_path(extends_name) if extends_name else None,
        "context_keys": sorted(context_keys),
        "partials": _collect_partials(env, template_name),
    }
