"""FastAPI dependency providers for the duplicate-check/verification services.

Mirrors `app.dependencies.product.get_product_service`'s cached-singleton
pattern. `ImageProcessingService`/`CatalogIntelligenceService`/
`DuplicateDetectionService` (which `DuplicateCheckService` composes
internally) get no provider of their own — nothing calls them directly
from a route, they're implementation details of this service, the same
reasoning `get_product_service`'s own docstring already established for
`ChecksumService`/`CLIPEmbeddingService`.

`get_duplicate_verification_service` (Phase 15) exposes the cross-encoder
+ business-rules verification pipeline the same way — one process-wide
singleton, consumed by `DuplicateCheckService` when
`DUPLICATE_VERIFICATION__ENABLED` is on.
"""

from functools import lru_cache

from app.services.duplicate.duplicate_check_service import DuplicateCheckService
from app.services.duplicate.duplicate_verification_service import DuplicateVerificationService


@lru_cache(maxsize=1)
def get_duplicate_check_service() -> DuplicateCheckService:
    """Return the process-wide DuplicateCheckService singleton, building it on first call."""
    return DuplicateCheckService()


@lru_cache(maxsize=1)
def get_duplicate_verification_service() -> DuplicateVerificationService:
    """Return the process-wide DuplicateVerificationService singleton, building it on first call."""
    return DuplicateVerificationService()
