"""Internal domain model: `ExplanationTrace`, the full explanation for one AI decision (Phase 16).

The unified output of the explanation layer, regardless of which
subsystem made the decision (hybrid search, reranking, duplicate
verification, recommendation, catalog intelligence): a natural-language
`summary`, the structured `reasons` behind it, an optional
`ConfidenceBreakdown` of how the score was composed, and a `confidence`.
`ExplanationService` builds these; `app/api/explanations.py` (Milestone 4)
serializes them into an `ExplanationResponse`.

`decision_type` is a plain string (`"hybrid_search"`/`"reranking"`/
`"duplicate"`/`"recommendation"`), not an enum — matching how
`BenchmarkReport.overall_metrics` keys by `EvaluationTaskType.value`
rather than the enum itself, so a report consumer never needs to import
an enum to read this. `subject_id` is the product (or query) the decision
was about, `None` for decisions not tied to a single stored entity.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason


class ExplanationTrace(BaseModel):
    """A human-readable, structured explanation of one AI decision."""

    decision_type: str = Field(min_length=1)
    summary: str
    subject_id: str | None = None
    reasons: list[DecisionReason] = Field(default_factory=list)
    breakdown: ConfidenceBreakdown | None = None
    confidence: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
