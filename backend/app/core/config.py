"""Typed application configuration with fail-fast validation.

Configuration is read once, validated eagerly, and cached. A misconfigured deployment must
fail at startup with a precise message rather than surface as a confusing runtime error on
the first request that happens to touch the bad value.

Environment groups follow `docs/02_BACKEND_ARCHITECTURE.md` §10.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import MIN_JWT_SECRET_LENGTH

AppEnv = Literal["development", "test", "production"]
StorageBackend = Literal["local", "s3"]

#: Markers of a secret that was never actually set. `.env.example` ships one deliberately so
#: a fresh clone runs locally; it must never survive into a deployed environment.
#: The word "secret" is not a marker — a genuine random value may contain it.
_PLACEHOLDER_SECRET_MARKERS = (
    "replace-with",
    "replace-me",
    "changeme",
    "change-me",
    "placeholder",
    "example",
    "insecure",
)

_VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class ConfigurationError(RuntimeError):
    """Raised when configuration is structurally valid but unusable in this environment."""


class Settings(BaseSettings):
    """Validated runtime settings.

    Instantiating this class never touches the filesystem or the network; call
    :meth:`ensure_directories` explicitly when the process needs its storage paths.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---------------------------------------------------------------
    app_env: AppEnv = "development"
    app_name: str = "BidPilot UAE"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:5173"

    # --- Database ------------------------------------------------------------------
    # Host ports match docker-compose.yml, which avoids 5432/6379 so the stack does not
    # collide with another project's PostgreSQL or Redis on the same machine.
    database_url: str = "postgresql+asyncpg://bidpilot:bidpilot@localhost:55432/bidpilot"

    # --- Redis / worker ------------------------------------------------------------
    redis_url: str = "redis://localhost:56379/0"

    # --- Authentication ------------------------------------------------------------
    jwt_secret: str = Field(min_length=MIN_JWT_SECRET_LENGTH)
    access_token_minutes: Annotated[int, Field(ge=1, le=1440)] = 15
    refresh_token_days: Annotated[int, Field(ge=1, le=90)] = 7
    password_min_length: Annotated[int, Field(ge=8, le=64)] = 12

    #: Refresh cookie attributes. `None` means "derive from APP_ENV", which keeps local
    #: development on http working while a deployed environment gets Secure cookies.
    refresh_cookie_name: str = "bidpilot_refresh"
    refresh_cookie_secure: bool | None = None
    refresh_cookie_samesite: Literal["lax", "strict", "none"] | None = None

    # --- Rate limiting -------------------------------------------------------------
    login_max_attempts: Annotated[int, Field(ge=1, le=1000)] = 10
    login_window_seconds: Annotated[int, Field(ge=10, le=86400)] = 300
    register_max_attempts: Annotated[int, Field(ge=1, le=1000)] = 5
    register_window_seconds: Annotated[int, Field(ge=10, le=86400)] = 3600

    # --- Storage and uploads -------------------------------------------------------
    storage_backend: StorageBackend = "local"
    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: Annotated[int, Field(ge=1024, le=200 * 1024 * 1024)] = 26_214_400
    max_pdf_pages: Annotated[int, Field(ge=1, le=2000)] = 200

    # --- OpenAI --------------------------------------------------------------------
    openai_api_key: str | None = None
    openai_model: str | None = None

    # --- Anthropic (optional; enabled after the primary workflow works) ------------
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None

    # --- AI behaviour and versioning -----------------------------------------------
    llm_timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 90
    llm_max_retries: Annotated[int, Field(ge=0, le=5)] = 2
    prompt_version: str = "1.0.0"
    scoring_version: str = "1.0.0"

    # --- Validators ----------------------------------------------------------------

    @field_validator("api_v1_prefix")
    @classmethod
    def _validate_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        if len(value) > 1 and value.endswith("/"):
            raise ValueError("API_V1_PREFIX must not end with '/'")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}")
        return level

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        # The whole persistence layer is async. A sync driver would fail deep inside
        # SQLAlchemy on first use, so reject it here where the message is actionable.
        if "+asyncpg" not in value:
            raise ValueError(
                "DATABASE_URL must use the asyncpg driver, "
                "e.g. postgresql+asyncpg://user:pass@host:5432/db"
            )
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL must start with redis://, rediss:// or unix://")
        return value

    @field_validator("upload_dir")
    @classmethod
    def _absolute_upload_dir(cls, value: Path) -> Path:
        # Stored document keys are built from this root; a relative path would resolve
        # differently for the API process and the worker process.
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def _reject_placeholder_secrets(self) -> Settings:
        if self.app_env == "development":
            return self
        lowered = self.jwt_secret.lower()
        if any(marker in lowered for marker in _PLACEHOLDER_SECRET_MARKERS):
            raise ValueError(
                f"JWT_SECRET still contains a placeholder value; set a real random secret "
                f"before running with APP_ENV={self.app_env}"
            )
        return self

    @model_validator(mode="after")
    def _samesite_none_requires_secure(self) -> Settings:
        # Browsers reject `SameSite=None` without `Secure`, silently dropping the refresh
        # cookie — a failure that looks like a broken login rather than a config mistake.
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "REFRESH_COOKIE_SAMESITE=none requires REFRESH_COOKIE_SECURE=true; "
                "browsers discard such cookies otherwise"
            )
        return self

    # --- Derived values -------------------------------------------------------------

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Explicit CORS allowlist. Never a wildcard, because refresh cookies are used."""
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    @property
    def log_level_number(self) -> int:
        return logging.getLevelNamesMapping()[self.log_level]

    @property
    def docs_enabled(self) -> bool:
        """Interactive docs are useful for a portfolio demo but off in production by default."""
        return not self.is_production

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies everywhere except local http development."""
        if self.refresh_cookie_secure is not None:
            return self.refresh_cookie_secure
        return not self.is_development

    @property
    def cookie_samesite(self) -> Literal["lax", "strict", "none"]:
        """`lax` locally; `none` when deployed, where API and frontend are different sites.

        `localhost:5173` and `localhost:8000` are the same site for cookie purposes (ports are
        ignored), so `lax` is sufficient in development and avoids requiring HTTPS.
        """
        if self.refresh_cookie_samesite is not None:
            return self.refresh_cookie_samesite
        return "lax" if self.is_development else "none"

    @property
    def refresh_cookie_path(self) -> str:
        """Scope the cookie to the auth routes so it is not attached to every request."""
        return f"{self.api_v1_prefix}/auth"

    def ensure_directories(self) -> None:
        """Create local storage directories. Called from process startup, not from import."""
        if self.storage_backend == "local":
            self.upload_dir.mkdir(parents=True, exist_ok=True)

    def require_openai(self) -> tuple[str, str]:
        """Return the OpenAI credentials, or explain precisely what is missing.

        Called by the provider adapter (Phase 6) so that a key-less environment produces a
        clear configuration error instead of an opaque authentication failure.
        """
        if not self.openai_api_key or not self.openai_model:
            raise ConfigurationError(
                "OPENAI_API_KEY and OPENAI_MODEL must both be set to run AI extraction"
            )
        return self.openai_api_key, self.openai_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance.

    The cache makes this safe to use as a FastAPI dependency and guarantees that every
    module sees identical configuration. Tests clear it via the `settings` fixture.
    """
    return Settings()
