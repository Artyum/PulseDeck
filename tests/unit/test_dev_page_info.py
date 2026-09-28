import inspect

from starlette.requests import Request
from starlette.routing import Route

from app.routes.auth import login_page
from app.routes.context import _templates
from app.utils.dev_page_info import build_dev_page_info


def _request(path: str, endpoint, *, route_path: str | None = None) -> Request:
    route = Route(route_path or path, endpoint=endpoint)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"host", b"testserver")],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "endpoint": endpoint,
            "route": route,
        }
    )


def test_build_dev_page_info_login_fields() -> None:
    request = _request("/login", login_page, route_path="/login")
    info = build_dev_page_info(request, _templates.env, "auth/login.html")
    expected_file = f"app/routes/auth.py:{inspect.getsourcelines(login_page)[1]}"
    assert info["url"] == "http://testserver/login"
    assert info["template"] == "frontend/templates/auth/login.html"
    assert "route" not in info
    assert info["file"] == expected_file
    assert "frontend/templates/base.html" not in info["partials"]
    assert "frontend/templates/partials/icons.html" not in info["partials"]
    assert "frontend/templates/partials/notice.html" in info["partials"]
    assert "frontend/templates/partials/app_flash.html" in info["partials"]
    assert info["api"] == ""
    assert info["js"] == ""
    assert "handler_qid" not in info
    assert "context_keys" not in info
    assert info["copy_text"].startswith("url: http://testserver/login")
    assert f"file: {expected_file}" in info["copy_text"]
    assert "route:" not in info["copy_text"]
