from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import get_settings, resolve_log_dir

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

_DOMAIN_FILES: tuple[tuple[str, str], ...] = (
    ("pulsedeck.app", "app.log"),
    ("pulsedeck.mail", "mail.log"),
    ("pulsedeck.db", "db.log"),
    ("pulsedeck.auth", "auth.log"),
    ("pulsedeck.reply_token", "auth.log"),
    ("pulsedeck.security", "security.log"),
)

_FILE_ONLY = frozenset({"pulsedeck.reply_token"})
_HEALTH_CHECK_PATHS = ("/api/health", "/healthz")


class HealthCheckAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not any(path in record.getMessage() for path in _HEALTH_CHECK_PATHS)


def silence_healthcheck_access_logs() -> None:
    filt = HealthCheckAccessLogFilter()
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, HealthCheckAccessLogFilter) for f in access.filters):
        access.addFilter(filt)


def _parse_level(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)


def _rotating_handler(path: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    return handler


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    settings = get_settings()
    level = _parse_level(settings.log_level)
    log_dir = resolve_log_dir()
    formatter = logging.Formatter(_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    ):
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(level)
        console.setFormatter(formatter)
        root.addHandler(console)

    error_handler = _rotating_handler(log_dir / "error.log", logging.ERROR)
    pulsedeck = logging.getLogger("pulsedeck")
    pulsedeck.setLevel(level)
    if error_handler not in pulsedeck.handlers:
        pulsedeck.addHandler(error_handler)

    handlers_by_file: dict[str, RotatingFileHandler] = {}
    for logger_name, filename in _DOMAIN_FILES:
        if filename not in handlers_by_file:
            handlers_by_file[filename] = _rotating_handler(log_dir / filename, level)
        lg = logging.getLogger(logger_name)
        lg.setLevel(level)
        handler = handlers_by_file[filename]
        if handler not in lg.handlers:
            lg.addHandler(handler)
        if logger_name in _FILE_ONLY:
            lg.propagate = False
            if error_handler not in lg.handlers:
                lg.addHandler(error_handler)

    db_handler = handlers_by_file["db.log"]
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = False
        if db_handler not in lg.handlers:
            lg.addHandler(db_handler)
        if error_handler not in lg.handlers:
            lg.addHandler(error_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("markdown_it").setLevel(logging.WARNING)
    silence_healthcheck_access_logs()
