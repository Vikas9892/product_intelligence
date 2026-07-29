"""Duplicate-check schemas: the API contract for `POST /products/check-duplicate` (Phase 8).

Deliberately separate from `app.models.duplicate_*` (the internal domain
models built by `SimilarityScorer`/`DuplicateDetectionService`) for the
same reason `app.schemas.product` is kept separate from
`app.models.product` — see that module's docstring. Never exposes a raw
embedding vector, matching every other response schema in this codebase
(`EmbeddingInfo`, `ProductSearchResult`, ...).

`DuplicateCheckResponse.duplicate` (not `is_duplicate`, unlike
`app.schemas.product.DuplicateInfo`) matches the phase spec's own literal
field name for this endpoint's output — `DuplicateInfo` predates this
endpoint and its own naming wasn't spec'd as precisely, so the two aren't
forced to agree.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class DuplicateCandidateInfo(BaseModel):
    """API-safe view of one ranked `app.models.duplicate_candidate.DuplicateCandidate`."""

    product_id: UUID
    image_similarity: float
    text_similarity: float
    metadata_similarity: float
    attribute_similarity: float
    overall_similarity: float


class DuplicateSignalBreakdown(BaseModel):
    """The winning candidate's four independent similarity signals.

    Derived from `DuplicateDecision.top_candidates[0]` (the same data
    `DuplicateCandidateInfo` above exposes per-candidate) — not a second,
    independent computation — so a caller doesn't have to reconstruct
    "which candidate won" from the `top_candidates` list themselves.
    """

    image: float
    text: float
    metadata: float
    attribute: float


class DuplicateCheckResponse(BaseModel):
    """Response body for `POST /api/v1/products/check-duplicate`.

    `signals`/`matched_product` are `None` when no candidate was found at
    all (an empty catalog, or a genuinely novel product) — there is no
    "winning" candidate to report on.

    `cross_encoder_score`/`retrieval_similarity`/`reasons` (Phase 15) are
    populated only when `DUPLICATE_VERIFICATION__ENABLED` is on: the
    cross-encoder relevance of the matched product, its raw embedding
    retrieval similarity, and the human-readable factors behind the
    verdict. When verification is off they stay `None`/empty — every
    pre-Phase-15 field keeps its exact meaning, so the response is
    backward compatible.
    """

    duplicate: bool
    confidence: float
    reason: str
    matched_product: UUID | None = None
    signals: DuplicateSignalBreakdown | None = None
    top_candidates: list[DuplicateCandidateInfo] = Field(default_factory=list)
    cross_encoder_score: float | None = None
    retrieval_similarity: float | None = None
    reasons: list[str] = Field(default_factory=list)
