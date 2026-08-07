"""Unit tests for `RecommendationExplainer`."""

from uuid import uuid4

import pytest

from app.core.config import settings
from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.services.explanations.recommendation_explainer import RecommendationExplainer


def _candidate(
    *,
    similarity_score: float = 0.9,
    attribute_score: float = 0.0,
    tag_score: float = 0.0,
    quality_score: float = 0.8,
    final_score: float = 0.88,
    reason: RecommendationReason | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        product_id=uuid4(),
        similarity_score=similarity_score,
        attribute_score=attribute_score,
        tag_score=tag_score,
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
        # Both original components are still published -- the breakdown gained
        # the two missing terms of the weighted sum, it did not lose any.
        assert {"similarity", "quality"}.issubset({c.name for c in trace.breakdown.components})

    def test_no_shared_signals_yields_a_bare_summary(self) -> None:
        trace = RecommendationExplainer().explain(_candidate(reason=RecommendationReason()))

        assert trace.reasons == []
        assert trace.summary == "Recommended because it shares."


def _breakdown(candidate: RecommendationCandidate) -> ConfidenceBreakdown:
    """Explain `candidate` and return its breakdown, narrowed from `| None`."""
    trace = RecommendationExplainer().explain(candidate)
    assert trace.breakdown is not None
    return trace.breakdown


class TestBreakdownArithmetic:
    """The published breakdown must actually add up to the score it explains.

    Regression tests for a panel whose arithmetic did not close: only two of
    the four components were published, both at a hardcoded weight of 1.0, so
    a real response showed similarity 0.57 and quality 0.64 against a total of
    0.51 -- a total below both displayed contributions, with 35% of the score
    invisible.
    """

    def test_publishes_every_component_of_the_weighted_sum(self) -> None:
        breakdown = _breakdown(_candidate())

        assert [c.name for c in breakdown.components] == [
            "similarity",
            "attribute_match",
            "tag_match",
            "quality",
        ]

    def test_component_weights_are_the_configured_weights_not_one(self) -> None:
        weights = {c.name: c.weight for c in _breakdown(_candidate()).components}

        assert weights == {
            "similarity": settings.recommendation.similarity_weight,
            "attribute_match": settings.recommendation.attribute_weight,
            "tag_match": settings.recommendation.tag_weight,
            "quality": settings.recommendation.quality_weight,
        }
        # The specific defect: everything was published at weight 1.0.
        assert all(weight != 1.0 for weight in weights.values())

    def test_contributions_sum_to_the_total(self) -> None:
        """The exact scenario from the reported run: 0.57 similarity, 0.64 quality."""
        similarity, attribute, tag, quality = 0.57, 0.40, 0.35, 0.64
        recommendation = settings.recommendation
        final = (
            recommendation.similarity_weight * similarity
            + recommendation.attribute_weight * attribute
            + recommendation.tag_weight * tag
            + recommendation.quality_weight * quality
        )

        breakdown = _breakdown(
            _candidate(
                similarity_score=similarity,
                attribute_score=attribute,
                tag_score=tag,
                quality_score=quality,
                final_score=final,
            )
        )

        summed = sum(component.contribution for component in breakdown.components)
        assert summed == pytest.approx(breakdown.total)
        # And the final really is lower than two of its own inputs -- correct,
        # because the weights are fractional. That was never the bug.
        assert breakdown.total < similarity
        assert breakdown.total < quality

    def test_contribution_is_value_times_weight(self) -> None:
        breakdown = _breakdown(
            _candidate(similarity_score=0.8, attribute_score=0.5, tag_score=0.2, quality_score=0.6)
        )

        for component in breakdown.components:
            assert component.contribution == pytest.approx(component.value * component.weight)
