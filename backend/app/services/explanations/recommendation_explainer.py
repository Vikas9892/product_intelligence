"""`RecommendationExplainer`: explains one recommendation (Phase 16).

Reads a `RecommendationCandidate` (Phase 9) — its similarity/quality/final
scores and the structured `RecommendationReason` (shared brand/category,
matched attributes, shared tags) — and produces an `ExplanationTrace`: the
score components as a `ConfidenceBreakdown` and the shared signals as
`DecisionReason`s, with a natural-language summary. Pure and read-only —
it explains a recommendation that was already scored and ranked.
"""

from app.core.config import settings
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

        # Every term of the weighted sum, with its real configured weight.
        #
        # This previously published only two of the four components, both at a
        # hardcoded weight of 1.0. The scorer's actual formula is
        #
        #     final = clamp(0.55*similarity + 0.20*attribute + 0.15*tag + 0.10*quality)
        #
        # so a reader saw "similarity 0.57 (weight 1.00)" and "quality 0.64
        # (weight 1.00)" against a final of 0.51 -- a total *below* both
        # displayed contributions, with the missing 35% of the score
        # (attribute + tag) not shown at all. The arithmetic could not be
        # followed, which defeats the purpose of an explainability panel.
        #
        # The weights are read from settings rather than restated here, so the
        # published breakdown cannot drift from the formula that produced the
        # score. Settings validates that they sum to 1.0 at startup, which is
        # what makes the contributions add up to the total.
        weights = settings.recommendation
        breakdown = self._builder.breakdown(
            [
                self._builder.weight(
                    "similarity", subject.similarity_score, weights.similarity_weight
                ),
                self._builder.weight(
                    "attribute_match", subject.attribute_score, weights.attribute_weight
                ),
                self._builder.weight("tag_match", subject.tag_score, weights.tag_weight),
                self._builder.weight("quality", subject.quality_score, weights.quality_weight),
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
