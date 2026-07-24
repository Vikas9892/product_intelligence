"""FastAPI dependency provider for `ProductService`.

Mirrors `app.dependencies.upload.get_upload_service`'s cached-singleton
pattern. `ChecksumService` (which `ProductService` composes internally)
gets no provider of its own — nothing calls it directly from a route, so
there's no seam FastAPI's dependency injection needs to provide; it's an
implementation detail of `ProductService`, not something a route ever
depends on independently.
"""

from functools import lru_cache

from app.services.product_service import ProductService


@lru_cache(maxsize=1)
def get_product_service() -> ProductService:
    """Return the process-wide ProductService singleton, building it on first call."""
    return ProductService()
