"""Explanation schemas: the API contract for the decision-trace endpoints (Phase 16).

Deliberately separate from `app.models.explanation_trace.ExplanationTrace`
(the internal domain model the explanation layer builds) for the same
reason every other API schema is kept separate from its domain model —
the wire contract is independent of the service's internal shape. The
endpoints (Milestone 4) map an `ExplanationTrace` into an
`ExplanationResponse`.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.explanation_trace import ExplanationTrace


class DecisionReasonInfo(BaseModel):
    """API-safe view of one `DecisionReason`."""

    code: str
    description: str
    weight: float | None = None


class DecisionWeightInfo(BaseModel):
    """API-safe view of one `DecisionWeight` contribution."""

    name: str
    value: float
    weight: float
    contribution: float


class ConfidenceBreakdownInfo(BaseModel):
    """API-safe view of a `ConfidenceBreakdown`."""

    components: list[DecisionWeightInfo] = Field(default_factory=list)
    total: float


class ExplanationResponse(BaseModel):
    """Response body for the decision-trace endpoints.

    `breakdown`/`confidence` are `None` when the decision had no composite
    score to break down (e.g. a purely qualitative explanation). `reasons`
    is the structured evidence; `summary` is the human-readable one-liner
    a caller can surface directly.
    """

    decision_type: str
    subject_id: str | None = None
    summary: str
    confidence: float | None = None
    reasons: list[DecisionReasonInfo] = Field(default_factory=list)
    breakdown: ConfidenceBreakdownInfo | None = None
    created_at: datetime

    @classmethod
    def from_trace(cls, trace: ExplanationTrace) -> "ExplanationResponse":
        """Build the API-safe view of `trace`."""
        return cls(
            decision_type=trace.decision_type,
            subject_id=trace.subject_id,
            summary=trace.summary,
            confidence=trace.confidence,
            reasons=[
                DecisionReasonInfo(code=r.code, description=r.description, weight=r.weight)
                for r in trace.reasons
            ],
            breakdown=(
                ConfidenceBreakdownInfo(
                    components=[
                        DecisionWeightInfo(
                            name=c.name,
                            value=c.value,
                            weight=c.weight,
                            contribution=c.contribution,
                        )
                        for c in trace.breakdown.components
                    ],
                    total=trace.breakdown.total,
                )
                if trace.breakdown is not None
                else None
            ),
            created_at=trace.created_at,
        )


class TraceBundleResponse(BaseModel):
    """A subject's ordered list of explanation traces (its "decision timeline").

    Used by `GET /recommendations/{id}/trace` — one `traces` entry per
    recommended product, newest decision first as produced by the engine.
    """

    subject_id: str
    count: int
    traces: list[ExplanationResponse] = Field(default_factory=list)


class ProductExplanationsResponse(BaseModel):
    """Aggregate explanation tree for one product (`GET /products/{id}/explanations`).

    Combines the product's duplicate-decision trace (`duplicate`, `None`
    when nothing to report) and its recommendation traces
    (`recommendations`) into one view — the full "why the platform decided
    what it did about this product."
    """

    product_id: str
    duplicate: ExplanationResponse | None = None
    recommendations: list[ExplanationResponse] = Field(default_factory=list)
