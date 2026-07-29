"""Unit tests for the `get_metrics_registry` dependency provider."""

from app.dependencies.metrics import get_metrics_registry
from app.metrics.metrics_registry import MetricsRegistry


class TestGetMetricsRegistry:
    def test_returns_a_metrics_registry_instance(self) -> None:
        get_metrics_registry.cache_clear()

        registry = get_metrics_registry()

        assert isinstance(registry, MetricsRegistry)

    def test_returns_a_cached_singleton(self) -> None:
        get_metrics_registry.cache_clear()

        first = get_metrics_registry()
        second = get_metrics_registry()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_metrics_registry.cache_clear()
        first = get_metrics_registry()

        get_metrics_registry.cache_clear()
        second = get_metrics_registry()

        assert first is not second
