"""FastAPI dependency provider for `SearchService`.

Mirrors `app.dependencies.product.get_product_service`'s cached-singleton
pattern. `BaseEmbeddingService`/`BaseVectorStore` (which `SearchService`
composes internally) get no provider of their own, for the same reason
`ProductService`'s composed services don't — nothing calls them directly
from a route.
"""

from functools import lru_cache

from app.services.vectorstore.search_service import SearchService


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    """Return the process-wide SearchService singleton, building it on first call."""
    return SearchService()
