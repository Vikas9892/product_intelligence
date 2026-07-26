"""Internal domain models for semantic product search (Phase 5).

Separate from `app.schemas.search` (the API contract) for the same reason
`app.models.product.Product` is kept separate from `app.schemas.product` —
see that module's docstring. `NearestNeighbor` is what
`app.services.vectorstore.base.BaseVectorStore.search` returns (one hit
from the vector store); `SearchQuery`/`SearchResult` mediate between
`SearchService` and the vector store.

`NearestNeighbor` is defined here first, ahead of the phase spec's own
milestone numbering (which lists "Search Domain Models" as Milestone 3,
after "Vector Store Abstraction" as Milestone 1) — `BaseVectorStore.search`
needs `NearestNeighbor` to already exist as its return type, so it's built
as a dependency of Milestone 1, the same "a milestone's dependencies get
built before the milestone that names them" reordering Phase 3/4 already
used for their own domain models.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NearestNeighbor(BaseModel):
    """One similar product found by a vector store search, ordered by descending score."""

    product_id: UUID
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    filters: dict[str, Any] | None = None


class SearchResult(BaseModel):
    """The outcome of one similarity search: which model was used, and what it found."""

    query_model_name: str
    neighbors: list[NearestNeighbor]
