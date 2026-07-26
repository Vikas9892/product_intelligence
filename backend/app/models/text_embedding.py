"""Internal domain model: `TextEmbedding`, a semantic vector for one product's text.

Mirrors `app.models.embedding.ImageEmbedding` (Phase 4) field-for-field —
`product_id`, `model_name`, `embedding_dimension`, `vector`, `created_at`
— rather than the phase spec's own literal field list (`embedding`,
`dimension`, `model_name`, `created_at`, no `product_id`). Deliberate:
`TextEmbedding` is attached to `Product` the exact same way
`ImageEmbedding` is (`Product.text_embedding`), so giving the two
domain models the same shape — same field names, same validation — is
more valuable than each phase's prose happening to word its field list
slightly differently. A future reader (or a function handling both
kinds of embedding generically) shouldn't have to remember that one
calls its vector `vector` and the other calls it `embedding`.

Separate from `app.schemas.product` for the same reason `ImageEmbedding`
is: never returned directly by any route.
"""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TextEmbedding(BaseModel):
    """A semantic vector produced by a text embedding model for one product's text."""

    product_id: UUID
    model_name: str
    embedding_dimension: int = Field(gt=0)
    vector: list[float]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_vector_length(self) -> "TextEmbedding":
        """Catch a mismatched embedding at construction time — see `ImageEmbedding`'s identical check."""
        if len(self.vector) != self.embedding_dimension:
            raise ValueError(
                f"vector length ({len(self.vector)}) does not match "
                f"embedding_dimension ({self.embedding_dimension})"
            )
        return self
