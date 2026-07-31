from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource
from sqlalchemy.engine import make_url

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEV_STORAGE_SECRET = "dev-only-change-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    storage_secret: str = _DEV_STORAGE_SECRET
    environment: str = "development"
    app_base_url: str = Field(
        default="http://localhost:8000", validation_alias="APP_BASE_URL"
    )
    log_dir: str = "logs"
    log_level: str = "DEBUG"
    upload_dir: str = "data/uploads"

    uvicorn_host: str = "127.0.0.1"
    uvicorn_port: int = 8000
    uvicorn_workers: int = 1
    uvicorn_proxy_headers: bool = False
    uvicorn_forwarded_allow_ips: str = "127.0.0.1"

    session_max_age_seconds: int = 8 * 60 * 60
    security_csrf_enabled: bool = True
    security_csp_enabled: bool = True
    security_hsts_enabled: bool = False
    auth_login_rate_limit: str = "10/minute"
    auth_forgot_password_rate_limit: str = "5/minute"
    auth_activate_rate_limit: str = "10/minute"
    auth_admin_user_create_rate_limit: str = "20/minute"
    upload_rate_limit: str = "20/minute"
    trusted_hosts: str = Field(
        default="localhost,127.0.0.1,pulsedeck.lan", validation_alias="ALLOWED_HOSTS"
    )

    admin_email: str = Field(default="", validation_alias="ADMIN_EMAIL")
    admin_password: str = Field(default="", validation_alias="ADMIN_PASSWORD")
    admin_first_name: str = Field(default="Admin", validation_alias="ADMIN_FIRST_NAME")
    admin_last_name: str = Field(
        default="PulseDeck", validation_alias="ADMIN_LAST_NAME"
    )

    smtp_server: str = ""
    smtp_port: int = 587
    smtp_use_ssl: bool = False
    smtp_user: str = ""
    smtp_pass: str = ""
    email_from: str = ""

    mail_min_interval_ms: int = Field(
        default=3000, validation_alias="MAIL_MIN_INTERVAL_MS"
    )
    mail_max_per_hour: int = Field(default=300, validation_alias="MAIL_MAX_PER_HOUR")
    mail_max_attempts: int = Field(default=5, validation_alias="MAIL_MAX_ATTEMPTS")
    mail_idle_ms: int = Field(default=1000, validation_alias="MAIL_IDLE_MS")

    auth_link_ttl_days: int = Field(default=7, validation_alias="AUTH_LINK_TTL_DAYS")
    email_confirm_ttl_minutes: int = Field(
        default=60, validation_alias="EMAIL_CONFIRM_TTL_MINUTES"
    )
    ticket_reopen_days: int = Field(default=7, validation_alias="TICKET_REOPEN_DAYS")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value

    @classmethod
    def settings_customise_sources(  # type: ignore[reportIncompatibleMethodOverride]
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings)

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        url = (self.database_url or "").strip()
        if not url:
            msg = "DATABASE_URL is empty. Set it in deploy/env/.env.dev (start_app.ps1) or Docker env."
            raise ValueError(msg)
        try:
            make_url(url)
        except Exception as exc:
            msg = f"DATABASE_URL is not a valid SQLAlchemy URL: {exc}"
            raise ValueError(msg) from exc

        if self.environment == "production" and (
            not self.storage_secret or self.storage_secret == _DEV_STORAGE_SECRET
        ):
            msg = "STORAGE_SECRET must be set to a strong value when ENVIRONMENT=production"
            raise ValueError(msg)

        self.app_base_url = self.app_base_url.strip().rstrip("/")
        return self

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_server.strip())

    @property
    def email_from_address(self) -> str:
        return (self.email_from or self.smtp_user).strip()

    def trusted_hosts_list(self) -> list[str]:
        hosts = [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]
        return hosts or ["localhost", "127.0.0.1"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def resolve_upload_dir() -> Path:
    settings = get_settings()
    path = Path(settings.upload_dir)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    return _PROJECT_ROOT
