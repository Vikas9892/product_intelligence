"""FastAPI dependency provider for `ExplanationService`.

Mirrors `app.dependencies.model_registry.get_model_registry`'s
cached-singleton pattern — one process-wide instance, built on first use.
`ExplanationBuilder` (which `ExplanationService` composes) gets no provider
of its own; nothing calls it directly from a route.
"""

from functools import lru_cache

from app.services.explanations.explanation_service import ExplanationService


@lru_cache(maxsize=1)
def get_explanation_service() -> ExplanationService:
    """Return the process-wide ExplanationService singleton, building it on first call."""
    return ExplanationService()
