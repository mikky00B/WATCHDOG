from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, EmailStr, Field, PostgresDsn, field_validator, model_validator
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
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
    )
    jwt_secret_key: str = Field(default="dev-only-change-this-secret")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=30)
    email_verification_code_expire_minutes: int = Field(default=15)
    password_reset_code_expire_minutes: int = Field(default=15)
    max_auth_attempts_per_window: int = Field(default=5)
    auth_rate_limit_window_seconds: int = Field(default=300)
    max_verification_attempts: int = Field(default=5)
    environment: str = Field(default="development")

    # Monitoring
    default_check_interval: int = Field(default=60, ge=10)
    default_timeout: float = Field(default=5.0, ge=1.0)
    max_concurrent_checks: int = Field(default=100)
    requests_per_minute_per_site: int = 10
    max_check_retries: int = 2
    run_scheduler_in_api: bool = Field(default=True)

    # Alerting - SMTP
    email_enabled: bool = False
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_use_tls: bool = Field(default=True)
    smtp_use_ssl: bool | None = Field(default=None)
    from_email: EmailStr | None = Field(
        default=None,
        validation_alias=AliasChoices("FROM_EMAIL", "SMTP_FROM_EMAIL"),
    )

    contact_email: EmailStr = Field(default="alerts@example.com")

    @model_validator(mode="after")
    def apply_derived_settings(self) -> Settings:
        if (
            self.environment.lower() in {"production", "prod"}
            and self.jwt_secret_key == "dev-only-change-this-secret"
        ):
            raise ValueError("JWT_SECRET_KEY must be set to a strong secret in production")
        if self.from_email is None and self.smtp_user:
            self.from_email = self.smtp_user
        if self.smtp_use_ssl is None:
            self.smtp_use_ssl = self.smtp_port == 465
        return self

    # Alerting - Slack
    slack_webhook_url: str | None = Field(default=None)

    # Alerting - Telegram
    telegram_bot_token: str | None = Field(default=None)
    telegram_webhook_secret: str | None = Field(default=None)
    telegram_webhook_url: str | None = Field(default=None)
    telegram_allowed_chat_ids: list[str] = []

    # Logging
    log_level: str = Field(default="INFO")

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def parse_telegram_chat_ids(cls, v: object) -> object:
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
