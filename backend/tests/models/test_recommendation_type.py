"""Unit tests for `RecommendationType`."""

from app.models.recommendation_type import RecommendationType


class TestRecommendationType:
    def test_has_the_three_expected_members(self) -> None:
        assert {member.value for member in RecommendationType} == {
            "similar",
            "related",
            "complementary",
        }

    def test_members_are_string_valued(self) -> None:
        assert RecommendationType.SIMILAR.value == "similar"
        assert RecommendationType.RELATED.value == "related"
        assert RecommendationType.COMPLEMENTARY.value == "complementary"
