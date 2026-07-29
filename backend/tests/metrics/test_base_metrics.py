"""Unit tests for `app.metrics.base_metrics`'s idempotent collector factories."""

from prometheus_client import CollectorRegistry

from app.metrics.base_metrics import (
    get_or_create_counter,
    get_or_create_gauge,
    get_or_create_histogram,
)


class TestGetOrCreateCounter:
    def test_creates_a_new_counter(self) -> None:
        registry = CollectorRegistry()

        counter = get_or_create_counter("a_counter", "desc", registry=registry)

        counter.inc()
        assert registry.get_sample_value("a_counter_total") == 1.0

    def test_returns_the_same_collector_on_a_second_call(self) -> None:
        registry = CollectorRegistry()

        first = get_or_create_counter("a_counter", "desc", registry=registry)
        second = get_or_create_counter("a_counter", "desc", registry=registry)

        assert first is second

    def test_does_not_raise_when_called_repeatedly_with_a_namespace(self) -> None:
        registry = CollectorRegistry()

        for _ in range(3):
            get_or_create_counter("a_counter", "desc", namespace="ns", registry=registry)

        assert registry.get_sample_value("ns_a_counter_total") == 0.0

    def test_creates_with_labels(self) -> None:
        registry = CollectorRegistry()

        counter = get_or_create_counter("labeled_counter", "desc", ["status"], registry=registry)

        counter.labels(status="ok").inc()
        assert registry.get_sample_value("labeled_counter_total", {"status": "ok"}) == 1.0


class TestGetOrCreateGauge:
    def test_creates_a_new_gauge(self) -> None:
        registry = CollectorRegistry()

        gauge = get_or_create_gauge("a_gauge", "desc", registry=registry)

        gauge.set(5)
        assert registry.get_sample_value("a_gauge") == 5.0

    def test_returns_the_same_collector_on_a_second_call(self) -> None:
        registry = CollectorRegistry()

        first = get_or_create_gauge("a_gauge", "desc", registry=registry)
        second = get_or_create_gauge("a_gauge", "desc", registry=registry)

        assert first is second


class TestGetOrCreateHistogram:
    def test_creates_a_new_histogram(self) -> None:
        registry = CollectorRegistry()

        histogram = get_or_create_histogram("a_histogram", "desc", registry=registry)

        histogram.observe(1.5)
        assert registry.get_sample_value("a_histogram_count") == 1.0

    def test_returns_the_same_collector_on_a_second_call(self) -> None:
        registry = CollectorRegistry()

        first = get_or_create_histogram("a_histogram", "desc", registry=registry)
        second = get_or_create_histogram("a_histogram", "desc", registry=registry)

        assert first is second
