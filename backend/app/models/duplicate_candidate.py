"""Internal domain model: `DuplicateCandidate`, one retrieved product's flattened similarity.

Distinct from `app.models.duplicate_result.DuplicateResult` (what
`SimilarityScorer` itself returns, carrying the full per-signal breakdown
with weights/contributions): `DuplicateCandidate` is the flatter, simpler
shape `DuplicateDecision.top_candidates` and `matched_product` actually
expose — just the four raw similarity scores plus the overall figure, no
weight bookkeeping a caller inspecting a decision doesn't need. See
`DuplicateDetectionService._to_candidate` for how one is derived from a
`DuplicateResult`.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class DuplicateCandidate(BaseModel):
    """One retrieved candidate product and its similarity to the product being checked."""

    product_id: UUID
    image_similarity: float = Field(ge=0, le=1)
    text_similarity: float = Field(ge=0, le=1)
    metadata_similarity: float = Field(ge=0, le=1)
    attribute_similarity: float = Field(ge=0, le=1)
    overall_similarity: float = Field(ge=0, le=1)
