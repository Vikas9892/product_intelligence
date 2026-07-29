"""FastAPI dependency provider for `MetricsRegistry`.

Mirrors `app.dependencies.model_registry.get_model_registry`'s
cached-singleton pattern. Every instrumented service still bare-constructs
its own default `MetricsRegistry()` when none is injected (the same
"sub-services aren't part of the DI graph themselves" reasoning
`get_model_registry`'s own docstring already establishes) — this provider
exists purely for `app/api/metrics.py`/`app/api/system.py`, the routes
that depend on `MetricsRegistry` directly.
"""

from functools import lru_cache

from app.metrics.metrics_registry import MetricsRegistry


@lru_cache(maxsize=1)
def get_metrics_registry() -> MetricsRegistry:
    """Return the process-wide MetricsRegistry singleton, building it on first call."""
    return MetricsRegistry()
