"""FastAPI dependency provider for `ModelRegistry`.

Mirrors `app.dependencies.hybrid_search.get_hybrid_search_service`'s
cached-singleton pattern. Unlike most services in this codebase,
`ModelRegistry` is also constructed *bare* (not via this provider) by
`CLIPEmbeddingService`/`SentenceTransformerEmbeddingService`/
`CrossEncoderService` when no `model_registry` is injected — those are
sub-services, never part of the FastAPI DI graph themselves, the same
reasoning `RerankerService` bare-constructs its own `CrossEncoderService`
default. This provider exists purely for `app/api/models.py`, the one
place a route depends on `ModelRegistry` directly.
"""

from functools import lru_cache

from app.services.model_registry import ModelRegistry


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """Return the process-wide ModelRegistry singleton, building it on first call."""
    return ModelRegistry()
