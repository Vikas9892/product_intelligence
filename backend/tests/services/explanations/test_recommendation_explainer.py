"""Unit tests for `RecommendationExplainer`."""

from uuid import uuid4

from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.services.explanations.recommendation_explainer import RecommendationExplainer


def _candidate(
    *,
    similarity_score: float = 0.9,
    quality_score: float = 0.8,
    final_score: float = 0.88,
    reason: RecommendationReason | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        product_id=uuid4(),
        similarity_score=similarity_score,
        quality_score=quality_score,
        final_score=final_score,
        reason=reason if reason is not None else RecommendationReason(),
    )


class TestRecommendationExplainer:
    def test_maps_shared_signals_into_reasons(self) -> None:
        candidate = _candidate(
            reason=RecommendationReason(
                shared_brand=True,
                shared_category=True,
                matched_attributes=["color", "material"],
                shared_tags=["running"],
            )
        )

        trace = RecommendationExplainer().explain(candidate)

        assert trace.decision_type == "recommendation"
        codes = {r.code for r in trace.reasons}
        assert codes == {"shared_brand", "shared_category", "matched_attributes", "shared_tags"}
        assert "the same brand" in trace.summary
        assert "matching color, material" in trace.summary

    def test_confidence_is_the_final_score(self) -> None:
        trace = RecommendationExplainer().explain(_candidate(final_score=0.88))

        assert trace.confidence == 0.88
        assert trace.breakdown is not None
        assert {c.name for c in trace.breakdown.components} == {"similarity", "quality"}

    def test_no_shared_signals_yields_a_bare_summary(self) -> None:
        trace = RecommendationExplainer().explain(_candidate(reason=RecommendationReason()))

        assert trace.reasons == []
        assert trace.summary == "Recommended because it shares."
