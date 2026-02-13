from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn, EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://monitoring_user:monitoring_pass@localhost:5432/monitoring_db"  # noqa: E501
    )

    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # Monitoring
    default_check_interval: int = Field(default=60, ge=10)
    default_timeout: float = Field(default=5.0, ge=1.0)
    max_concurrent_checks: int = Field(default=100)
    requests_per_minute_per_site: int = 10
    max_check_retries: int = 2

    # Alerting - SMTP
    email_enabled: bool = False
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_from_email: str | None = Field(default=None)
    from_email: EmailStr = "alerts@example.com"
    alert_emails: list[EmailStr] = []

    contact_email: str = "Clevermike02@gmail.com"

    @field_validator("alert_emails", mode="before")
    @classmethod
    def parse_alert_emails(cls, v):
        """Parse comma-separated email list from env."""
        if isinstance(v, str):
            # Handle comma-separated string from .env
            return [email.strip() for email in v.split(",") if email.strip()]
        return v

    # Alerting - Slack
    slack_webhook_url: str | None = Field(default=None)

    # Alerting - Telegram
    telegram_bot_token: str | None = Field(default=None)
    telegram_webhook_secret: str | None = Field(default=None)
    telegram_allowed_chat_ids: list[str] = []

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def parse_telegram_chat_ids(cls, v):
        """Parse comma-separated chat ID list from env."""
        if isinstance(v, str):
            return [chat_id.strip() for chat_id in v.split(",") if chat_id.strip()]
        if isinstance(v, int):
            return [str(v)]
        if isinstance(v, list):
            return [str(chat_id).strip() for chat_id in v if str(chat_id).strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
