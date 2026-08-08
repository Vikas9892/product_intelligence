"""FastAPI dependency provider for `ProductService`.

Mirrors `app.dependencies.upload.get_upload_service`'s cached-singleton
pattern. `ChecksumService` and `CLIPEmbeddingService` (which `ProductService`
composes internally) get no provider of their own — nothing calls them
directly from a route, so there's no seam FastAPI's dependency injection
needs to provide; they're implementation details of `ProductService`, not
something a route ever depends on independently. This also gives
`CLIPEmbeddingService`'s `ModelManager` its "loaded once" guarantee for
free — see `app/services/embeddings/model_manager.py`'s docstring — since
`ProductService` itself is built exactly once, here, behind `lru_cache`.
"""

from functools import lru_cache

from app.services.product_image_service import ProductImageService
from app.services.product_lookup_service import ProductLookupService
from app.services.product_service import ProductService


@lru_cache(maxsize=1)
def get_product_service() -> ProductService:
    """Return the process-wide ProductService singleton, building it on first call."""
    return ProductService()


@lru_cache(maxsize=1)
def get_product_lookup_service() -> ProductLookupService:
    """Return the process-wide `ProductLookupService` singleton.

    The read counterpart to `get_product_service`, and cached for the same
    reason: it holds a vector-store client and no per-request state.
    """
    return ProductLookupService()


@lru_cache(maxsize=1)
def get_product_image_service() -> ProductImageService:
    """Return the process-wide `ProductImageService` singleton."""
    return ProductImageService()
