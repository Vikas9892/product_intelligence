"""API schemas for reading an indexed product back by ID.

Why this exists
---------------

Recommendations, duplicate matches and search traces all return *product IDs*.
Until now nothing could turn an ID back into a name: the API exposed upload,
status, search, recommendations, duplicates, explanations and pricing, but no
`GET /products/{id}`. A client holding an ID had no way to resolve it, so the
frontend rendered every recommendation card as "Unresolved product".

The capability existed one layer down the whole time -- `BaseVectorStore`
already offers `retrieve_image`/`retrieve_text`, returning the stored payload
with name, brand, category, price, colour, tags and quality score. Only the
route was missing.

Why a batch endpoint rather than embedding products in the recommendation
response
-------------------------------------------------------------------------

Embedding full product objects inside `RecommendationsResponse` was the
alternative, and it was rejected deliberately:

* It duplicates the same product in every response that mentions it -- a
  recommendation list, a duplicate decision and a search result would each
  carry their own copy, and they would drift.
* It bloats payloads that are otherwise small and cacheable. Recommendation
  responses are worker-precomputed and cached in Redis; embedding mutable
  product metadata inside them means the cache holds stale names.
* It does not help the other views that face exactly the same problem --
  duplicates and explanations also return bare IDs.

A separate lookup keeps each response describing its own decision, lets the
client cache products independently of the decisions that reference them, and
serves every view with one endpoint. The batch variant exists so a view
resolving N cards makes one request rather than N.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

#: Ceiling on `POST /products/batch`. Bounded because the endpoint fans out to
#: one vector-store lookup per ID: an unbounded list would let a single request
#: issue arbitrarily many. 100 comfortably covers any realistic view (the
#: largest today asks for ~10) while keeping the worst case cheap.
MAX_BATCH_SIZE = 100


class ProductSummary(BaseModel):
    """An indexed product's catalog metadata, as stored alongside its vectors.

    Deliberately a *summary*: it carries what a client needs to render and
    reason about a product, not the internals. Filesystem paths and raw
    embeddings are never exposed here -- the same rule
    `ProcessedImageInfo` already documents for image paths.
    """

    product_id: UUID
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    price: float | None = None
    description: str | None = None
    color: str | None = None
    material: str | None = None
    gender: str | None = None
    season: str | None = None
    style: str | None = None
    tags: list[str] = Field(default_factory=list)
    quality_score: float | None = None

    @classmethod
    def from_metadata(cls, product_id: UUID, metadata: dict[str, Any]) -> "ProductSummary":
        """Build a summary from a stored vector payload.

        Every field is optional and coerced defensively: the payload is
        written by the ingestion pipeline, and a product indexed by an older
        build may simply not carry a newer field. A missing attribute should
        render as absent, not fail the request.
        """
        return cls(
            product_id=product_id,
            name=_as_str(metadata.get("name")),
            brand=_as_str(metadata.get("brand")),
            category=_as_str(metadata.get("category")),
            price=_as_float(metadata.get("price")),
            description=_as_str(metadata.get("description")),
            color=_as_str(metadata.get("color")),
            material=_as_str(metadata.get("material")),
            gender=_as_str(metadata.get("gender")),
            season=_as_str(metadata.get("season")),
            style=_as_str(metadata.get("style")),
            tags=[tag for tag in metadata.get("tags", []) if isinstance(tag, str)],
            quality_score=_as_float(metadata.get("quality_score")),
        )


class ProductBatchRequest(BaseModel):
    """A request to resolve several product IDs at once."""

    product_ids: list[UUID] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Product IDs to resolve. At most {MAX_BATCH_SIZE}.",
    )


class ProductBatchResponse(BaseModel):
    """The products that resolved, and the IDs that did not.

    Unknown IDs are reported rather than silently omitted, and the endpoint
    does not 404 for them: a partially-stale recommendation list is a normal
    state, and a client resolving ten cards should still render the nine that
    exist. `missing` lets it show a real "product not found" state for the
    tenth instead of an ambiguous placeholder.
    """

    products: list[ProductSummary] = Field(default_factory=list)
    missing: list[UUID] = Field(default_factory=list)
    resolved_at: datetime


def _as_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
