"""Search schemas: the response contract for `POST /api/v1/products/search`.

Deliberately separate from `app.models.search` (Phases 5-6's internal
domain models) for the same reason `app.schemas.product` is kept separate
from `app.models.product` — see that module's docstring. `ProductSearchResult`
mirrors `app.models.search.HybridSearchResult`'s fields closely, but as
its own type: the API response is a contract this codebase controls
independently of whatever shape the search pipeline happens to return
internally. `matched_modalities` is plain `list[str]` here rather than
reusing `app.models.search.SearchModality` directly — an API response
schema shouldn't be coupled to how an internal enum happens to be
defined today.
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
    `matched_modalities` (Phase 6) tells a caller whether a result matched
    on image, text, or both, without revealing anything about *how*.
    """

    product_id: UUID
    score: float
    matched_modalities: list[str]
    metadata: dict[str, Any]


class ProductSearchResponse(BaseModel):
    """Response body for `POST /api/v1/products/search`."""

    results: list[ProductSearchResult]
