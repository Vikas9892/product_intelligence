"""Unit tests for the settings singleton in app.core.config."""

from app.core import config
from app.core.settings import Settings


def test_get_settings_returns_a_cached_singleton() -> None:
    config.get_settings.cache_clear()

    first = config.get_settings()
    second = config.get_settings()

    assert first is second


def test_cache_clear_forces_a_fresh_instance() -> None:
    config.get_settings.cache_clear()
    first = config.get_settings()

    config.get_settings.cache_clear()
    second = config.get_settings()

    assert first is not second
    assert first == second  # same values, just a different object


def test_module_level_settings_is_a_settings_instance() -> None:
    assert isinstance(config.settings, Settings)
