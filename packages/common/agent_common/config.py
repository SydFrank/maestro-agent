"""Centralised configuration via pydantic-settings.

Every service subclasses ``BaseServiceSettings`` and adds its own fields.
Values are read from environment variables (and a local ``.env`` in dev).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Settings shared by every service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "service"
    log_level: str = "INFO"

    # Infra
    redis_url: str = "redis://redis:6379/0"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "agent"
    postgres_password: str = "agent_pwd"
    postgres_db: str = "agent_platform"

    # Observability
    otel_exporter_otlp_endpoint: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
