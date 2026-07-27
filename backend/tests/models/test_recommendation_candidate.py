"""Unit tests for `RecommendationCandidate`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason


class TestRecommendationCandidate:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        reason = RecommendationReason(matched_attributes=["color"], shared_brand=True)

        candidate = RecommendationCandidate(
            product_id=product_id,
            similarity_score=0.9,
            quality_score=0.7,
            final_score=0.85,
            reason=reason,
            explanation="Similar visual appearance.",
        )

        assert candidate.product_id == product_id
        assert candidate.similarity_score == 0.9
        assert candidate.quality_score == 0.7
        assert candidate.final_score == 0.85
        assert candidate.reason == reason
        assert candidate.explanation == "Similar visual appearance."

    def test_explanation_defaults_to_empty_string(self) -> None:
        candidate = RecommendationCandidate(
            product_id=uuid4(),
            similarity_score=0.5,
            quality_score=0.5,
            final_score=0.5,
            reason=RecommendationReason(),
        )

        assert candidate.explanation == ""

    def test_rejects_a_final_score_above_one(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.5,
                quality_score=0.5,
                final_score=1.5,
                reason=RecommendationReason(),
            )

    def test_rejects_a_negative_similarity_score(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=-0.1,
                quality_score=0.5,
                final_score=0.5,
                reason=RecommendationReason(),
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        candidate = RecommendationCandidate(
            product_id=uuid4(),
            similarity_score=0.9,
            quality_score=0.7,
            final_score=0.85,
            reason=RecommendationReason(shared_category=True),
            explanation="Same category.",
        )

        dumped = candidate.model_dump(mode="json")
        restored = RecommendationCandidate.model_validate(dumped)

        assert restored == candidate
