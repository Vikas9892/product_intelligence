"""Unit tests for the configuration schema in app.core.settings."""

import pytest
from pydantic import ValidationError

from app.core.constants import Environment, LogLevel
from app.core.settings import ApplicationSettings, SecuritySettings, Settings


class TestApplicationSettings:
    def test_defaults(self) -> None:
        settings = ApplicationSettings()
        assert settings.environment is Environment.LOCAL
        assert settings.debug is True
        assert settings.port == 8000

    def test_rejects_out_of_range_port(self) -> None:
        with pytest.raises(ValidationError):
            ApplicationSettings(port=70000)


class TestSecuritySettings:
    def test_rejects_short_secret_key(self) -> None:
        with pytest.raises(ValidationError, match="at least 16 characters"):
            SecuritySettings(secret_key="too-short")

    def test_accepts_sufficiently_long_secret_key(self) -> None:
        key = "a" * 32
        settings = SecuritySettings(secret_key=key)
        assert settings.secret_key.get_secret_value() == key

    def test_secret_key_is_not_exposed_in_repr(self) -> None:
        settings = SecuritySettings(secret_key="a" * 32)
        assert "a" * 32 not in repr(settings)
        assert "**********" in repr(settings)


class TestSettingsComposition:
    def test_default_local_settings_are_valid(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.application.environment is Environment.LOCAL
        assert settings.application.debug is True
        assert settings.logging.level is LogLevel.INFO
        assert settings.database.url.startswith("sqlite")

    def test_env_vars_override_nested_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APPLICATION__PORT", "9999")
        monkeypatch.setenv("LOGGING__LEVEL", "DEBUG")

        settings = Settings(_env_file=None)

        assert settings.application.port == 9999
        assert settings.logging.level is LogLevel.DEBUG

    def test_production_requires_overridden_secret_key(self) -> None:
        with pytest.raises(ValidationError, match="secret_key must be overridden"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": False},
                database={"url": "postgresql://user:pass@host/db"},
            )

    def test_production_rejects_debug_true(self) -> None:
        with pytest.raises(ValidationError, match="debug must be false"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": True},
                database={"url": "postgresql://user:pass@host/db"},
                security={"secret_key": "a-properly-long-production-secret-key"},
            )

    def test_production_rejects_sqlite_database(self) -> None:
        with pytest.raises(ValidationError, match="must not be SQLite"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": False},
                security={"secret_key": "a-properly-long-production-secret-key"},
            )

    def test_production_accepts_a_fully_overridden_config(self) -> None:
        settings = Settings(
            _env_file=None,
            application={"environment": "production", "debug": False},
            database={"url": "postgresql://user:pass@host/db"},
            security={"secret_key": "a-properly-long-production-secret-key"},
        )

        assert settings.application.environment is Environment.PRODUCTION
        assert settings.application.debug is False
