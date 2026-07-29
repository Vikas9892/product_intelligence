"""Internal domain model: `ConfidenceBreakdown`, how a confidence score was composed (Phase 16).

Groups the per-signal `DecisionWeight`s that add up to a decision's final
`total` confidence, so an explanation can show *how* a number was
reached (embedding 0.7·0.6 + text 0.9·0.4 = ...) rather than just
asserting it. Purely descriptive — building one never recomputes the
decision, it only records the arithmetic the decision already did.
"""

from pydantic import BaseModel, Field

from app.models.decision_weight import DecisionWeight


class ConfidenceBreakdown(BaseModel):
    """The weighted components behind a composite confidence score, and their total."""

    components: list[DecisionWeight] = Field(default_factory=list)
    total: float
