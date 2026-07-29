"""`RecommendationExplainer`: explains one recommendation (Phase 16).

Reads a `RecommendationCandidate` (Phase 9) — its similarity/quality/final
scores and the structured `RecommendationReason` (shared brand/category,
matched attributes, shared tags) — and produces an `ExplanationTrace`: the
score components as a `ConfidenceBreakdown` and the shared signals as
`DecisionReason`s, with a natural-language summary. Pure and read-only —
it explains a recommendation that was already scored and ranked.
"""

from app.models.decision_reason import DecisionReason
from app.models.explanation_trace import ExplanationTrace
from app.models.recommendation_candidate import RecommendationCandidate
from app.services.explanations.base_explainer import BaseExplainer
from app.services.explanations.explanation_builder import ExplanationBuilder


class RecommendationExplainer(BaseExplainer[RecommendationCandidate]):
    """Explains why a product was recommended, from its shared signals and scores."""

    def __init__(self, *, builder: ExplanationBuilder | None = None) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()

    def explain(self, subject: RecommendationCandidate) -> ExplanationTrace:
        """Explain why `subject` was recommended."""
        reason = subject.reason
        reasons: list[DecisionReason] = []
        if reason.shared_brand:
            reasons.append(DecisionReason(code="shared_brand", description="the same brand"))
        if reason.shared_category:
            reasons.append(DecisionReason(code="shared_category", description="the same category"))
        if reason.matched_attributes:
            reasons.append(
                DecisionReason(
                    code="matched_attributes",
                    description=f"matching {', '.join(reason.matched_attributes)}",
                )
            )
        if reason.shared_tags:
            reasons.append(
                DecisionReason(
                    code="shared_tags",
                    description=f"shared tags ({', '.join(reason.shared_tags)})",
                )
            )

        breakdown = self._builder.breakdown(
            [
                self._builder.weight("similarity", subject.similarity_score, 1.0),
                self._builder.weight("quality", subject.quality_score, 1.0),
            ],
            total=subject.final_score,
        )

        return ExplanationTrace(
            decision_type="recommendation",
            summary=self._builder.summarize("Recommended because it shares", reasons),
            subject_id=str(subject.product_id),
            reasons=reasons,
            breakdown=breakdown,
            confidence=subject.final_score,
        )
