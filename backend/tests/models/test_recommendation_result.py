"""Unit tests for `RecommendationResult`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType


def _candidate(final_score: float = 0.9) -> RecommendationCandidate:
    return RecommendationCandidate(
        product_id=uuid4(),
        similarity_score=final_score,
        quality_score=final_score,
        final_score=final_score,
        reason=RecommendationReason(),
    )


class TestRecommendationResult:
    def test_constructs_with_all_fields(self) -> None:
        recommendations = [_candidate(0.9), _candidate(0.8)]

        result = RecommendationResult(
            recommendations=recommendations,
            processing_time=0.05,
            recommendation_type=RecommendationType.SIMILAR,
        )

        assert result.recommendations == recommendations
        assert result.processing_time == 0.05
        assert result.recommendation_type is RecommendationType.SIMILAR

    def test_recommendations_defaults_to_empty_list(self) -> None:
        result = RecommendationResult(
            processing_time=0.0, recommendation_type=RecommendationType.RELATED
        )

        assert result.recommendations == []

    def test_rejects_a_negative_processing_time(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationResult(
                processing_time=-0.1, recommendation_type=RecommendationType.SIMILAR
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = RecommendationResult(
            recommendations=[_candidate()],
            processing_time=0.02,
            recommendation_type=RecommendationType.SIMILAR,
        )

        dumped = result.model_dump(mode="json")
        restored = RecommendationResult.model_validate(dumped)

        assert restored == result
