"""Unit tests for the `get_model_registry` dependency provider."""

from app.dependencies.model_registry import get_model_registry
from app.services.model_registry import ModelRegistry


class TestGetModelRegistry:
    def test_returns_a_model_registry_instance(self) -> None:
        get_model_registry.cache_clear()

        registry = get_model_registry()

        assert isinstance(registry, ModelRegistry)

    def test_returns_a_cached_singleton(self) -> None:
        get_model_registry.cache_clear()

        first = get_model_registry()
        second = get_model_registry()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_model_registry.cache_clear()
        first = get_model_registry()

        get_model_registry.cache_clear()
        second = get_model_registry()

        assert first is not second
