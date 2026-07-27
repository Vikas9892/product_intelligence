"""Unit tests for the recommendation schemas."""

from uuid import uuid4

from app.schemas.recommendation import (
    RecommendationInfo,
    RecommendationReasonInfo,
    RecommendationsResponse,
)


class TestRecommendationReasonInfo:
    def test_defaults(self) -> None:
        reason = RecommendationReasonInfo()

        assert reason.matched_attributes == []
        assert reason.matched_tags == []
        assert reason.shared_brand is False
        assert reason.shared_category is False

    def test_constructs_with_all_fields(self) -> None:
        reason = RecommendationReasonInfo(
            matched_attributes=["color"],
            matched_tags=["running"],
            shared_brand=True,
            shared_category=True,
        )

        assert reason.matched_attributes == ["color"]
        assert reason.matched_tags == ["running"]


class TestRecommendationsResponse:
    def test_round_trips_through_model_dump_and_validate(self) -> None:
        response = RecommendationsResponse(
            recommendation_type="similar",
            recommendations=[
                RecommendationInfo(
                    product_id=uuid4(),
                    score=0.9,
                    reason=RecommendationReasonInfo(shared_brand=True),
                    explanation="Similar visual appearance.",
                )
            ],
        )

        dumped = response.model_dump(mode="json")
        restored = RecommendationsResponse.model_validate(dumped)

        assert restored == response

    def test_recommendations_defaults_to_empty_list(self) -> None:
        response = RecommendationsResponse(recommendation_type="similar")

        assert response.recommendations == []
