from typing import cast

from starlette.requests import Request

from app.middleware.security_headers import (
    _content_security_policy,
    _request_is_https,
    _request_is_secure_context,
)


def _make_request(*, scheme="http", host="example.com", x_forwarded_proto=None):
    headers = {}
    if x_forwarded_proto is not None:
        headers["x-forwarded-proto"] = x_forwarded_proto
    url = type("URL", (), {"scheme": scheme, "hostname": host})()
    return cast(
        Request,
        type(
            "Request",
            (),
            {
                "url": url,
                "headers": headers,
                "method": "GET",
            },
        )(),
    )


class TestRequestIsHttps:
    def test_scheme_https(self):
        assert _request_is_https(_make_request(scheme="https")) is True

    def test_x_forwarded_proto_https(self):
        req = _make_request(scheme="http", x_forwarded_proto="https")
        assert _request_is_https(req) is True

    def test_http(self):
        assert _request_is_https(_make_request(scheme="http")) is False

    def test_x_forwarded_proto_http(self):
        req = _make_request(x_forwarded_proto="http")
        assert _request_is_https(req) is False


class TestRequestIsSecureContext:
    def test_https_is_secure(self):
        assert _request_is_secure_context(_make_request(scheme="https")) is True

    def test_localhost_is_secure(self):
        assert _request_is_secure_context(_make_request(host="localhost")) is True

    def test_127_0_0_1_is_secure(self):
        assert _request_is_secure_context(_make_request(host="127.0.0.1")) is True

    def test_loopback_is_secure(self):
        assert _request_is_secure_context(_make_request(host="::1")) is True

    def test_sub_localhost_is_secure(self):
        assert _request_is_secure_context(_make_request(host="app.localhost")) is True

    def test_production_http_not_secure(self):
        assert _request_is_secure_context(_make_request(host="example.com")) is False


class TestContentSecurityPolicy:
    def test_default(self):
        csp = _content_security_policy()
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "style-src" in csp
        assert "font-src" in csp
        assert "img-src 'self' data: blob:" in csp
        assert "upgrade-insecure-requests" not in csp

    def test_with_upgrade(self):
        csp = _content_security_policy(upgrade_insecure=True)
        assert "upgrade-insecure-requests" in csp

    def test_has_form_action(self):
        csp = _content_security_policy()
        assert "form-action 'self'" in csp
