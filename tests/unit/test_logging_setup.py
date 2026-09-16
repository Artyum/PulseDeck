"""Testy konfiguracji logowania."""

from __future__ import annotations

import logging

from app.logging_setup import HealthCheckAccessLogFilter


def test_healthcheck_access_log_filter() -> None:
    filt = HealthCheckAccessLogFilter()
    health = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '127.0.0.1:12345 - "GET /api/health HTTP/1.1" 200',
        (),
        None,
    )
    other = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '127.0.0.1:12345 - "GET /api/auth/login HTTP/1.1" 200',
        (),
        None,
    )
    assert filt.filter(health) is False
    assert filt.filter(other) is True
