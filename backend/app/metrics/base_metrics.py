"""Idempotent `prometheus_client` collector factories (Phase 14).

`MetricsRegistry` (this package's own consumer) is bare-constructed the
same way every other sub-service in this codebase is — `ModelRegistry()`,
`HybridSearchService()`, ... — which means it can run its constructor
more than once per process (once per `create_app()` call in the test
suite, for instance). A plain `Counter(...)`/`Gauge(...)`/`Histogram(...)`
call raises `ValueError: Duplicated timeseries` the *second* time the
same metric name is registered into the same `CollectorRegistry` — fatal
for anything using the process-wide default `REGISTRY` `prometheus_client`
itself defaults to (and which `GET /metrics`, via
`prometheus-fastapi-instrumentator`, must keep using, since that's the
one registry actually exposed).

These three functions make that safe: each looks up whether a collector
with this exact name already exists in `registry` (via its private but
stable `_names_to_collectors` mapping — the same lookup
`prometheus_client` itself uses internally to detect the collision) and
returns the existing collector instead of registering a duplicate. The
*first* caller in the process still creates the real collector; every
later caller (a second `MetricsRegistry()`, a second `create_app()` in
the test suite) transparently gets the same one back.
"""

from collections.abc import Sequence

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Gauge, Histogram


def _existing_name(registry: CollectorRegistry, *, namespace: str, name: str) -> str:
    return f"{namespace}_{name}" if namespace else name


def get_or_create_counter(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    *,
    namespace: str = "",
    registry: CollectorRegistry = REGISTRY,
) -> Counter:
    """Return the `Counter` named `name` in `registry`, creating it on first call."""
    existing = registry._names_to_collectors.get(
        _existing_name(registry, namespace=namespace, name=name)
    )
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, documentation, labelnames, namespace=namespace, registry=registry)


def get_or_create_gauge(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    *,
    namespace: str = "",
    registry: CollectorRegistry = REGISTRY,
) -> Gauge:
    """Return the `Gauge` named `name` in `registry`, creating it on first call."""
    existing = registry._names_to_collectors.get(
        _existing_name(registry, namespace=namespace, name=name)
    )
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, documentation, labelnames, namespace=namespace, registry=registry)


def get_or_create_histogram(
    name: str,
    documentation: str,
    labelnames: Sequence[str] = (),
    *,
    namespace: str = "",
    registry: CollectorRegistry = REGISTRY,
) -> Histogram:
    """Return the `Histogram` named `name` in `registry`, creating it on first call."""
    existing = registry._names_to_collectors.get(
        _existing_name(registry, namespace=namespace, name=name)
    )
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Histogram(name, documentation, labelnames, namespace=namespace, registry=registry)
