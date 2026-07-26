"""Internal domain model: `DuplicateDecision`, the final duplicate-detection verdict.

Built exclusively by `DuplicateDetectionService` (`app/services/duplicate/
duplicate_detection_service.py`) from a list of `DuplicateResult`s (one
per retrieved candidate, each already scored by `SimilarityScorer`) — see
that service's own docstring for the full pipeline. This is the type
`ProductService` acts on (store/warn/block) and what `POST /products/
check-duplicate` (Milestone 5) ultimately returns.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.duplicate_candidate import DuplicateCandidate


class DuplicateDecision(BaseModel):
    """Whether a product is likely a duplicate, and the evidence behind that call.

    `matched_product`/`confidence` describe the single best-matching
    candidate (`None`/`0.0` when no candidate cleared the configured
    threshold); `top_candidates` carries every candidate considered,
    highest similarity first, so a caller (or the WARN-mode response) can
    inspect the full picture rather than just the winner.
    """

    is_duplicate: bool
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_product: UUID | None = None
    top_candidates: list[DuplicateCandidate] = Field(default_factory=list)
