"""Internal domain model: `ImageEmbedding`, a semantic vector for one product image.

Separate from `app.schemas.product` for the same reason `ImageMetadata` and
`Product` are: `vector` is a 512-float (or whatever `embedding_dimension`
is) raw array that has no reason to ever reach an HTTP response body —
`app/api/products.py` maps only `model_name`/`embedding_dimension` onto an
API-facing schema, never `vector` itself.

Built exclusively by `ProductService` (`app/services/product_service.py`)
from the output of `CLIPEmbeddingService.generate_embedding`, and attached
to `Product` (`app/models/product.py`) as `Product.embedding`.
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ImageEmbedding(BaseModel):
    """A semantic vector produced by an embedding model for one product's image."""

    product_id: UUID
    model_name: str
    embedding_dimension: int = Field(gt=0)
    vector: list[float]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_vector_length(self) -> "ImageEmbedding":
        """Catch a mismatched embedding at construction time, not on first use.

        A vector whose length silently disagreed with its declared
        `embedding_dimension` would be a bug in whatever built this model
        (`CLIPEmbeddingService` returning something inconsistent with what
        it reported) — better to fail loudly here than let it surface
        later as a confusing shape mismatch downstream.
        """
        if len(self.vector) != self.embedding_dimension:
            raise ValueError(
                f"vector length ({len(self.vector)}) does not match "
                f"embedding_dimension ({self.embedding_dimension})"
            )
        return self
