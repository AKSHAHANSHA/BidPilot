"""Configuration must fail fast and loudly on anything unusable."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, Settings

VALID_SECRET = "unit-test-jwt-value-0123456789abcdefghij"
VALID_DB = "postgresql+asyncpg://user:pass@localhost:5432/db"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every settings variable from the process environment.

    `tests/conftest.py` exports a full test configuration so the API suite never touches a
    real database. These tests assert on defaults and validators, so they must see a blank
    environment — otherwise they would silently test conftest's values instead.
    """
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
        monkeypatch.delenv(field, raising=False)


def build(**overrides: object) -> Settings:
    """Construct Settings from explicit values only, ignoring any local .env file."""
    values: dict[str, object] = {"jwt_secret": VALID_SECRET, "database_url": VALID_DB}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_defaults_are_usable_for_local_development() -> None:
    settings = build()
    assert settings.app_env == "development"
    assert settings.is_development is True
    assert settings.docs_enabled is True
    assert settings.api_v1_prefix == "/api/v1"


def test_jwt_secret_is_required() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, database_url=VALID_DB)  # type: ignore[call-arg]
    assert "jwt_secret" in str(exc_info.value)


def test_short_jwt_secret_rejected() -> None:
    with pytest.raises(ValidationError):
        build(jwt_secret="too-short")


def test_placeholder_secret_rejected_outside_development() -> None:
    placeholder = "replace-with-a-long-random-value"
    # Accepted locally so a fresh clone runs from .env.example without edits...
    assert build(jwt_secret=placeholder, app_env="development").app_env == "development"
    # ...but never in a deployed environment.
    for environment in ("production", "test"):
        with pytest.raises(ValidationError, match="placeholder"):
            build(jwt_secret=placeholder, app_env=environment)


def test_sync_database_url_rejected() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        build(database_url="postgresql://user:pass@localhost:5432/db")


def test_unknown_app_env_rejected() -> None:
    with pytest.raises(ValidationError):
        build(app_env="staging")


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        build(log_level="chatty")


def test_log_level_is_normalized_and_mapped() -> None:
    settings = build(log_level="debug")
    assert settings.log_level == "DEBUG"
    assert settings.log_level_number == 10


def test_invalid_redis_url_rejected() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        build(redis_url="localhost:6379")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_upload_bytes", 10),  # below the 1 KiB floor
        ("max_upload_bytes", 500 * 1024 * 1024),  # above the 200 MiB ceiling
        ("max_pdf_pages", 0),
        ("llm_timeout_seconds", 1),
        ("llm_max_retries", 9),
        ("access_token_minutes", 0),
        ("refresh_token_days", 0),
    ],
)
def test_bounded_numeric_settings(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        build(**{field: value})


@pytest.mark.parametrize("prefix", ["api/v1", "/api/v1/"])
def test_api_prefix_shape_enforced(prefix: str) -> None:
    with pytest.raises(ValidationError, match="API_V1_PREFIX"):
        build(api_v1_prefix=prefix)


def test_upload_dir_is_absolute() -> None:
    settings = build(upload_dir="./data/uploads")
    assert settings.upload_dir.is_absolute()


def test_cors_origins_parses_comma_separated_allowlist() -> None:
    settings = build(frontend_origin="http://localhost:5173, https://bidpilot.example ")
    assert settings.cors_origins == ["http://localhost:5173", "https://bidpilot.example"]


def test_docs_disabled_in_production() -> None:
    settings = build(app_env="production", jwt_secret=VALID_SECRET)
    assert settings.docs_enabled is False
    assert settings.is_production is True


def test_development_cookies_work_over_plain_http() -> None:
    # localhost:5173 and localhost:8000 are the same site for cookies, so `lax` is enough and
    # no HTTPS is required to sign in locally.
    settings = build(app_env="development")
    assert settings.cookie_samesite == "lax"
    assert settings.cookie_secure is False


def test_deployed_cookies_are_cross_site_capable_and_secure() -> None:
    # API and frontend live on different domains when deployed, so the refresh cookie must be
    # SameSite=None — which browsers only accept together with Secure.
    settings = build(app_env="production")
    assert settings.cookie_samesite == "none"
    assert settings.cookie_secure is True


def test_cookie_attributes_can_be_overridden() -> None:
    settings = build(refresh_cookie_samesite="strict", refresh_cookie_secure=True)
    assert settings.cookie_samesite == "strict"
    assert settings.cookie_secure is True


def test_samesite_none_without_secure_is_rejected() -> None:
    """A browser silently discards such a cookie, which looks like a broken login."""
    with pytest.raises(ValidationError, match="requires REFRESH_COOKIE_SECURE"):
        build(refresh_cookie_samesite="none", refresh_cookie_secure=False)


def test_refresh_cookie_path_is_scoped_to_the_auth_routes() -> None:
    # A cookie scoped to "/" would ride along on every API request for no reason.
    assert build().refresh_cookie_path == "/api/v1/auth"
    assert build(api_v1_prefix="/api/v2").refresh_cookie_path == "/api/v2/auth"


def test_require_openai_reports_missing_configuration() -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        build().require_openai()


def test_require_openai_returns_key_and_model() -> None:
    settings = build(openai_api_key="sk-test", openai_model="gpt-test")
    assert settings.require_openai() == ("sk-test", "gpt-test")
