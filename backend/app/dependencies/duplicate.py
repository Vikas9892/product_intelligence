"""FastAPI dependency provider for `DuplicateCheckService`.

Mirrors `app.dependencies.product.get_product_service`'s cached-singleton
pattern. `ImageProcessingService`/`CatalogIntelligenceService`/
`DuplicateDetectionService` (which `DuplicateCheckService` composes
internally) get no provider of their own — nothing calls them directly
from a route, they're implementation details of this service, the same
reasoning `get_product_service`'s own docstring already established for
`ChecksumService`/`CLIPEmbeddingService`.
"""

from functools import lru_cache

from app.services.duplicate.duplicate_check_service import DuplicateCheckService


@lru_cache(maxsize=1)
def get_duplicate_check_service() -> DuplicateCheckService:
    """Return the process-wide DuplicateCheckService singleton, building it on first call."""
    return DuplicateCheckService()
