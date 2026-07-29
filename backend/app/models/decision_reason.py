"""Internal domain model: `DecisionReason`, one explainable factor behind any AI decision (Phase 16).

The general-purpose successor to the phase-specific reason types this
codebase already produces (`VerificationReason`, `RerankReason`, the
booleans/lists on `RecommendationReason`): a single, self-describing
"why" that the explanation layer can build regardless of which subsystem
made the decision. Carries a stable machine `code` (for a caller that
branches on the reason type) and a human-readable `description` (the
sentence fragment surfaced in an explanation), plus an optional `weight`
recording how much this factor mattered to the decision.

Deliberately independent of business logic: nothing in
`HybridSearchService`/`DuplicateVerificationService`/
`RecommendationEngineService` depends on this type — the explanation
layer (Phase 16) *reads* their outputs and maps them into
`DecisionReason`s, never the other way around.
"""

from pydantic import BaseModel, Field


class DecisionReason(BaseModel):
    """One human-readable factor behind an AI decision, with an optional importance weight."""

    #: Stable machine-readable slug, e.g. "same_brand", "high_embedding_similarity".
    code: str = Field(min_length=1)
    #: Human-readable sentence fragment, e.g. "Same brand (Nike)".
    description: str = Field(min_length=1)
    #: How much this factor influenced the decision, in `[0, 1]` — `None`
    #: when the factor is qualitative (a match/mismatch) rather than weighted.
    weight: float | None = Field(default=None, ge=0, le=1)
