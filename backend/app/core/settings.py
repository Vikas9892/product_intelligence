"""Typed, validated application configuration schema.

Settings are grouped by concern (application, database, AI models, storage,
security, logging) as nested `BaseModel`s, then composed into one
`Settings` root that `pydantic-settings` populates from environment
variables and a `.env` file. Nested groups are addressed with a `__`
delimiter, e.g.:

    APPLICATION__PORT=8000
    DATABASE__URL=postgresql://...
    SECURITY__SECRET_KEY=...

This module defines the *schema* only — it does not instantiate `Settings`
or decide caching. That's `app.core.config`'s job. Keeping the two separate
means this file has no side effects and every class in it can be
constructed directly in a unit test without touching real environment
variables or `.env`.
"""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import constants, paths


class ApplicationSettings(BaseModel):
    """Core app identity and HTTP server settings."""

    name: str = constants.DEFAULT_APP_NAME
    version: str = constants.DEFAULT_APP_VERSION
    environment: constants.Environment = constants.Environment.LOCAL
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = constants.API_V1_PREFIX


class DatabaseSettings(BaseModel):
    """Primary datastore connection.

    Defaults to a relative SQLite file so the app runs with zero config
    locally. Production must override this — enforced in
    `Settings._validate_production_safety` below.
    """

    url: str = "sqlite+aiosqlite:///./storage/app.db"
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=100)


class AIModelSettings(BaseModel):
    """External AI provider configuration.

    No AI calls are made yet (that starts in later phases) — this just
    reserves the shape so `.env` doesn't need to change when they arrive.
    """

    openai_api_key: SecretStr | None = None
    embedding_model: str = "text-embedding-3-small"
    llm_model: str = "gpt-4o-mini"
    request_timeout_seconds: float = Field(default=30.0, gt=0)


class StorageSettings(BaseModel):
    """Local/object storage for uploaded product assets."""

    upload_dir: Path = paths.UPLOAD_DIR
    max_upload_size_mb: int = Field(default=constants.DEFAULT_UPLOAD_MAX_SIZE_MB, gt=0)
    allowed_image_extensions: tuple[str, ...] = constants.SUPPORTED_IMAGE_EXTENSIONS


class SecuritySettings(BaseModel):
    """Auth/crypto configuration."""

    secret_key: SecretStr = SecretStr(constants.INSECURE_DEFAULT_SECRET_KEY)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("secret_key")
    @classmethod
    def _minimum_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("security.secret_key must be at least 16 characters long")
        return value


class LoggingSettings(BaseModel):
    """Logging behaviour."""

    level: constants.LogLevel = constants.LogLevel.INFO
    json_logs: bool = False


class Settings(BaseSettings):
    """Root settings object composed of the grouped settings above.

    Precedence (highest to lowest): constructor kwargs > environment
    variables > `.env` file > the field defaults declared on each group.
    """

    model_config = SettingsConfigDict(
        env_file=str(paths.ENV_FILE),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    application: ApplicationSettings = Field(default_factory=ApplicationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai_models: AIModelSettings = Field(default_factory=AIModelSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        """Fail fast at startup if production is misconfigured.

        Silently "correcting" an insecure production config (e.g. forcing
        debug off) would hide the mistake instead of catching it — raising
        here turns a misconfigured deploy into an immediate boot failure.
        """
        if self.application.environment is constants.Environment.PRODUCTION:
            if self.security.secret_key.get_secret_value() == constants.INSECURE_DEFAULT_SECRET_KEY:
                raise ValueError(
                    "security.secret_key must be overridden in production "
                    "(SECURITY__SECRET_KEY) — the insecure default is not allowed."
                )
            if self.application.debug:
                raise ValueError("application.debug must be false in production.")
            if self.database.url.lower().startswith("sqlite"):
                raise ValueError(
                    "database.url must not be SQLite in production "
                    "(DATABASE__URL) — SQLite is a local/dev/test-only store."
                )
        return self
