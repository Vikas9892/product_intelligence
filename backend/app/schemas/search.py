"""Search schemas: the response contract for `POST /api/v1/products/search`.

Deliberately separate from `app.models.search` (Phase 5's internal domain
models) for the same reason `app.schemas.product` is kept separate from
`app.models.product` — see that module's docstring. `ProductSearchResult`
mirrors `app.models.search.NearestNeighbor`'s fields exactly, but as its
own type: the API response is a contract this codebase controls
independently of whatever shape the vector store happens to return
internally.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProductSearchResult(BaseModel):
    """One similar product found for a search query.

    Deliberately excludes the query's or the match's raw embedding vector
    — nothing outside this codebase has a use for a raw float array today,
    and returning one would leak internal representation for no benefit
    (the same "don't expose data a client can't act on yet" reasoning
    `EmbeddingInfo`, Phase 4, already established for the upload response).
    """

    product_id: UUID
    score: float
    metadata: dict[str, Any]


class ProductSearchResponse(BaseModel):
    """Response body for `POST /api/v1/products/search`."""

    results: list[ProductSearchResult]
