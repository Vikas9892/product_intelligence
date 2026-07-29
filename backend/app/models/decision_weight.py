"""Internal domain model: `DecisionWeight`, one weighted score contribution in a decision (Phase 16).

The general-purpose successor to `SimilaritySignal` (Phase 8): a named
signal's raw value, the weight applied to it, and its resulting
contribution to the final score. Unlike `SimilaritySignal`, its `value`
isn't constrained to `[0, 1]` — a cross-encoder logit or a fused hybrid
score the explanation layer wants to surface can legitimately fall
outside that range — so this stays a faithful record of "what this signal
contributed," whatever the number was.

`ConfidenceBreakdown` groups a list of these into the full accounting of
how a confidence score was composed.
"""

from pydantic import BaseModel, Field


class DecisionWeight(BaseModel):
    """One named signal's value, its weight, and its contribution to a composite score."""

    name: str = Field(min_length=1)
    value: float
    weight: float
    contribution: float
