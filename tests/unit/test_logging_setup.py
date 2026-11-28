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


def test_mail_logger_writes_smtp_log_not_app_log(tmp_path, monkeypatch) -> None:
    from app import logging_setup
    from app.config import get_settings

    settings = get_settings().model_copy(update={"log_level": "INFO"})
    monkeypatch.setattr(logging_setup, "get_settings", lambda: settings)
    monkeypatch.setattr(logging_setup, "resolve_log_dir", lambda: tmp_path)
    logging_setup._CONFIGURED = False
    for name in ("pulsedeck", "pulsedeck.mail", "pulsedeck.app"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        logger.propagate = True
    logging_setup.setup_logging()
    logging.getLogger("pulsedeck.mail").info("mail-marker")
    logging.getLogger("pulsedeck.mail.mfa").info("mfa-mail-marker")
    logging.getLogger("pulsedeck.app").info("app-marker")
    for name in ("pulsedeck.mail", "pulsedeck.app"):
        for handler in logging.getLogger(name).handlers:
            handler.flush()
    smtp_text = (tmp_path / "smtp.log").read_text(encoding="utf-8")
    app_text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "mail-marker" in smtp_text
    assert "mfa-mail-marker" in smtp_text
    assert "mail-marker" not in app_text
    assert "mfa-mail-marker" not in app_text
    assert "app-marker" not in smtp_text
    assert logging.getLogger("pulsedeck.mail").propagate is False
