"""Internal domain model: `DuplicateResult`, `SimilarityScorer`'s per-candidate output.

Informally called a "SimilarityReport" in the Phase 8 spec's own
Milestone 2 narrative — implemented here as `DuplicateResult` (the file
the spec's own Milestone 1 file list names) rather than introducing a
fifth, near-duplicate model name for the same concept. This is the
*detailed* comparison result for one candidate (every `SimilaritySignal`,
each with its own weight/contribution) that `SimilarityScorer.score`
returns; `DuplicateDetectionService` reduces it down to the flatter
`app.models.duplicate_candidate.DuplicateCandidate` for anything exposed
on a `DuplicateDecision`.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.similarity_signal import SimilaritySignal


class DuplicateResult(BaseModel):
    """The full similarity comparison between a new product and one candidate."""

    product_id: UUID
    signals: list[SimilaritySignal] = Field(default_factory=list)
    #: `sum(signal.contribution for signal in signals)`, clamped to `[0, 1]`.
    overall_similarity: float = Field(ge=0, le=1)
