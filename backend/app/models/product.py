"""Internal domain model: a `Product`, independent of any HTTP transport.

Distinct from `app.schemas.product` on purpose. The schemas module defines
the *API contract* — shaped by what's convenient to send as multipart form
fields or JSON, and coupled to FastAPI (`ProductCreate` is bound via
`Form()`, `UploadResponse` is a `response_model`). This module defines the
*business concept* "Product" — what `ProductService` actually builds and,
once a persistence layer exists, what will be mapped to/from a database
row. The two are expected to diverge over time (the API adds
backward-compatible fields; the domain model gains internal-only ones)
without either having to change in lockstep.

Both happen to be implemented with pydantic's `BaseModel` — that's an
implementation detail (convenient validation/serialization), not what
makes them different. The separation is architectural (which layer a type
belongs to, and why it would change), not a difference in technology.

`Product` is never returned directly by a route — `app/api/products.py`
maps its fields onto `UploadResponse` instead, so a route always returns
an explicit, versioned API shape rather than leaking the internal model.
"""

from uuid import UUID

from pydantic import BaseModel

from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.embedding import ImageEmbedding
from app.models.image_metadata import ImageMetadata
from app.models.text_embedding import TextEmbedding
from app.utils.metadata import FileMetadata


class Product(BaseModel):
    """A fully processed, normalized product — identified, but not yet persisted.

    Built exclusively by `ProductService` (`app/services/product_service.py`)
    from already-normalized, already-validated fields — see
    `app/validators/product_validator.py` for why this model itself
    doesn't re-declare field constraints (`ProductCreate` validates the
    raw input; the validators re-check the normalized result; by the time
    a `Product` is constructed, both have already run).
    """

    id: UUID
    name: str
    brand: str | None
    description: str | None
    category: str | None
    price: float | None
    file_metadata: FileMetadata
    #: Populated by `ImageProcessingService` (Phase 3) — always present,
    #: since every upload is processed before a `Product` is built.
    image_metadata: ImageMetadata
    #: Populated by `CLIPEmbeddingService` (Phase 4) — always present,
    #: since every upload is embedded right after image processing.
    embedding: ImageEmbedding
    #: Populated by `SentenceTransformerEmbeddingService` (Phase 6) —
    #: always present, generated immediately after the image embedding
    #: from the product's name/brand/category/description.
    text_embedding: TextEmbedding
    #: Populated by `CatalogIntelligenceService` (Phase 7) — always
    #: present, even when catalog intelligence is disabled via settings
    #: (an empty `ProductAttributes`/no tags/zero quality score, rather
    #: than making this field itself optional).
    catalog_intelligence: CatalogIntelligenceResult
