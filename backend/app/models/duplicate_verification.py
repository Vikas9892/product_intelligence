"""Internal domain model: `DuplicateVerification`, the cross-encoder + business-rules verdict (Phase 15).

The richer successor to `DuplicateDecision` (Phase 8) for the
verification pipeline: where `DuplicateDecision` reports a single weighted
`confidence`, a `DuplicateVerification` separates the two signals that
produced the verdict — the cross-encoder relevance score
(`cross_encoder_score`) and the raw embedding retrieval similarity
(`retrieval_similarity`) — and carries the human-readable
`reasons` behind the call (`VerificationReason` list). Built by
`DuplicateVerificationService`; surfaced (backward-compatibly) through the
extended `POST /products/check-duplicate` response.

`cross_encoder_score`/`retrieval_similarity` are `None` when verification
didn't run (e.g. `DUPLICATE_VERIFICATION__ENABLED` off, or no candidate
was retrieved at all) — a caller can tell "verification produced no
cross-encoder signal" apart from "the cross-encoder scored it 0.0".
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.duplicate_candidate import DuplicateCandidate
from app.models.verification_reason import VerificationReason


class DuplicateVerification(BaseModel):
    """Whether a product is a duplicate, the two signals behind it, and the explainable reasons."""

    is_duplicate: bool
    confidence: float = Field(ge=0, le=1)
    cross_encoder_score: float | None = None
    retrieval_similarity: float | None = None
    matched_product: UUID | None = None
    reasons: list[VerificationReason] = Field(default_factory=list)
    top_candidates: list[DuplicateCandidate] = Field(default_factory=list)
