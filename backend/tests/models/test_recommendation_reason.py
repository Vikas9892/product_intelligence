"""Unit tests for `RecommendationReason`."""

from app.models.recommendation_reason import RecommendationReason


class TestRecommendationReason:
    def test_constructs_with_all_fields(self) -> None:
        reason = RecommendationReason(
            matched_attributes=["color", "material"],
            shared_tags=["running", "red"],
            shared_brand=True,
            shared_category=True,
        )

        assert reason.matched_attributes == ["color", "material"]
        assert reason.shared_tags == ["running", "red"]
        assert reason.shared_brand is True
        assert reason.shared_category is True

    def test_defaults_are_empty_and_false(self) -> None:
        reason = RecommendationReason()

        assert reason.matched_attributes == []
        assert reason.shared_tags == []
        assert reason.shared_brand is False
        assert reason.shared_category is False

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        reason = RecommendationReason(
            matched_attributes=["color"], shared_tags=["running"], shared_brand=True
        )

        dumped = reason.model_dump(mode="json")
        restored = RecommendationReason.model_validate(dumped)

        assert restored == reason
