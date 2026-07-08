"""Application settings, loaded from the environment (see repo `.env.example`)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ────────────────────────────────────────────────────────────────
    app_name: str = "Vyakhya Studio API"
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    # Origins allowed by CORS (the Vite/TanStack dev server during development).
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])
    # Directory of the built frontend to serve in production (optional).
    frontend_dist: str | None = Field(default=None, alias="FRONTEND_DIST")

    # ── Security ───────────────────────────────────────────────────────────
    # Master key used to derive the symmetric key that encrypts provider API
    # keys at rest. Provisioned by ./setup.sh into .env. Required in production;
    # a dev default keeps local boots working without secrets.
    encryption_key: str = Field(default="dev-insecure-key", alias="VYAKHYA_ENCRYPTION_KEY")
    # Shared API key gating /api routes. Provisioned by ./setup.sh. When empty,
    # auth is disabled (dev convenience) — a startup warning is logged.
    api_key: str = Field(default="", alias="VYAKHYA_API_KEY")

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://vyakhya:change-me@localhost:5432/vyakhya",
        alias="DATABASE_URL",
    )

    # ── Object storage (MinIO / S3) ────────────────────────────────────────
    s3_endpoint: str = Field(default="http://localhost:9000", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="vyakhya", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="change-me", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="vyakhya", alias="S3_BUCKET")

    # ── Render service ─────────────────────────────────────────────────────
    render_service_url: str = Field(default="http://localhost:8080", alias="RENDER_SERVICE_URL")
    # When true, real renders are delegated to the Node render service; otherwise
    # the in-process simulated executor is used (dev default).
    use_render_service: bool = Field(default=False, alias="USE_RENDER_SERVICE")
    # Shared key sent to the render service (must match its RENDER_API_KEY).
    render_api_key: str = Field(default="", alias="RENDER_API_KEY")

    # ── Execution ──────────────────────────────────────────────────────────
    # When true, run the pipeline/render in-process (no Procrastinate worker
    # needed) — convenient for dev and the current simulated executors.
    inprocess_jobs: bool = Field(default=True, alias="INPROCESS_JOBS")

    @property
    def sqlalchemy_url(self) -> str:
        """Normalize the URL to the asyncpg driver SQLAlchemy expects."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def is_encryption_key_secure(self) -> bool:
        return self.encryption_key not in ("", "dev-insecure-key")

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
