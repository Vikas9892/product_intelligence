"""Internal domain models for semantic product search (Phases 5-6).

Separate from `app.schemas.search` (the API contract) for the same reason
`app.models.product.Product` is kept separate from `app.schemas.product` —
see that module's docstring. `NearestNeighbor` is what
`app.services.vectorstore.base.BaseVectorStore.search` returns (one hit
from the vector store); `ProductFilters` is what a search can be
restricted by; `SearchQuery`/`SearchResult` mediate between `SearchService`
and the vector store.

`NearestNeighbor` is defined here first, ahead of the phase spec's own
milestone numbering (which lists "Search Domain Models" as Milestone 3,
after "Vector Store Abstraction" as Milestone 1) — `BaseVectorStore.search`
needs `NearestNeighbor` to already exist as its return type, so it's built
as a dependency of Milestone 1, the same "a milestone's dependencies get
built before the milestone that names them" reordering Phase 3/4 already
used for their own domain models.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NearestNeighbor(BaseModel):
    """One similar product found by a vector store search, ordered by descending score."""

    product_id: UUID
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProductFilters(BaseModel):
    """Metadata filters applicable to a vector search.

    Equality on `brand`/`category`, range on price (`min_price`/
    `max_price`) — replaces Phase 5's loose `filters: dict[str, Any]`
    contract (`{"category": "shoes"}`) now that price needs a *range*
    condition a flat equality dict can't cleanly express without
    inventing a mini query-DSL inside dict values, which would be worse
    than just typing the filter properly. All fields are optional; a
    filter left as `None` doesn't restrict results at all.
    """

    brand: str | None = None
    category: str | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)


class SearchQuery(BaseModel):
    """A fully-resolved similarity search request.

    Built by `SearchService` right after it embeds the query image —
    bundles the resolved vector together with the search parameters and
    which model produced it, so the rest of the search pipeline (logging,
    calling `BaseVectorStore.search`) works with one well-typed object
    instead of several loose positional arguments.
    """

    vector: list[float]
    model_name: str
    top_k: int = Field(gt=0)
    filters: ProductFilters | None = None


class SearchResult(BaseModel):
    """The outcome of one similarity search: which model was used, and what it found."""

    query_model_name: str
    neighbors: list[NearestNeighbor]


class SearchModality(StrEnum):
    """Which query type (Phase 6) contributed to a hybrid search match.

    Deliberately a separate type from `app.services.vectorstore.base.VectorCollection`
    even though both are currently just "image"/"text" — reusing
    `VectorCollection` here would mean this module importing from
    `app.services.vectorstore.base`, which already imports `NearestNeighbor`/
    `ProductFilters` *from* this module; that would be a circular import.
    The two enums also mean different things (which Qdrant collection an
    operation targets, vs. which query modality matched a hybrid search
    result) that only happen to share the same two values today.
    """

    IMAGE = "image"
    TEXT = "text"


class HybridSearchResult(BaseModel):
    """One product found by a hybrid (or single-modality) search, with its fused score.

    `matched_modalities` records which query type(s) actually found this
    product — `["image"]`/`["text"]` for a single-modality search,
    potentially both for a hybrid one, so a caller can tell a result that
    matched on both image and text apart from one that only matched on
    one side.
    """

    product_id: UUID
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    matched_modalities: list[SearchModality]
