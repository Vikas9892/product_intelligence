"""Unit tests for `RecommendationScorer`."""

from uuid import uuid4

import pytest

from app.models.search import HybridSearchResult, SearchModality
from app.services.recommendation.recommendation_scorer import RecommendationScorer


def _candidate(
    *, score: float = 0.9, metadata: dict[str, object] | None = None
) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=uuid4(),
        score=score,
        metadata=metadata if metadata is not None else {},
        matched_modalities=[SearchModality.IMAGE, SearchModality.TEXT],
    )


def _scorer(
    *,
    similarity_weight: float = 0.55,
    attribute_weight: float = 0.20,
    tag_weight: float = 0.15,
    quality_weight: float = 0.10,
) -> RecommendationScorer:
    return RecommendationScorer(
        similarity_weight=similarity_weight,
        attribute_weight=attribute_weight,
        tag_weight=tag_weight,
        quality_weight=quality_weight,
    )


class TestIdenticalProducts:
    def test_identical_metadata_scores_near_one(self) -> None:
        target_metadata = {
            "brand": "Nike",
            "category": "running-shoes",
            "color": "Red",
            "material": "Mesh",
            "gender": "Men",
            "season": "Summer",
            "style": "Running",
            "tags": ["running", "red", "lightweight"],
            "quality_score": 0.9,
        }
        candidate = _candidate(score=1.0, metadata=dict(target_metadata))
        scorer = _scorer()

        result = scorer.score(target_metadata=target_metadata, candidate=candidate)

        assert result.final_score > 0.95
        assert result.reason.shared_brand is True
        assert result.reason.shared_category is True
        assert set(result.reason.matched_attributes) == {
            "color",
            "material",
            "gender",
            "season",
            "style",
        }
        assert set(result.reason.shared_tags) == {"running", "red", "lightweight"}


class TestDifferentBrands:
    def test_a_different_brand_is_not_flagged_as_shared(self) -> None:
        target_metadata = {"brand": "Nike", "category": "running-shoes"}
        candidate = _candidate(metadata={"brand": "Adidas", "category": "running-shoes"})
        scorer = _scorer()

        result = scorer.score(target_metadata=target_metadata, candidate=candidate)

        assert result.reason.shared_brand is False
        assert result.reason.shared_category is True

    def test_conflicting_attributes_are_excluded_from_matched_attributes(self) -> None:
        target_metadata = {"color": "Red", "material": "Mesh"}
        candidate = _candidate(metadata={"color": "Blue", "material": "Mesh"})
        scorer = _scorer()

        result = scorer.score(target_metadata=target_metadata, candidate=candidate)

        assert result.reason.matched_attributes == ["material"]


class TestBlankValues:
    def test_a_whitespace_only_brand_on_both_sides_is_not_flagged_as_shared(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"brand": "   "})

        result = scorer.score(target_metadata={"brand": "   "}, candidate=candidate)

        assert result.reason.shared_brand is False

    def test_a_blank_candidate_attribute_is_excluded_from_matched_attributes(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"color": "   "})

        result = scorer.score(target_metadata={"color": "Red"}, candidate=candidate)

        assert result.reason.matched_attributes == []


class TestMissingTags:
    def test_no_tags_on_either_side_yields_a_zero_tag_score_not_a_crash(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={})

        result = scorer.score(target_metadata={}, candidate=candidate)

        assert result.reason.shared_tags == []

    def test_tags_missing_only_on_the_candidate_yields_no_shared_tags(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"tags": []})

        result = scorer.score(target_metadata={"tags": ["running", "red"]}, candidate=candidate)

        assert result.reason.shared_tags == []

    def test_partial_tag_overlap_is_reflected_in_the_final_score(self) -> None:
        scorer = _scorer(
            similarity_weight=0.0, attribute_weight=0.0, tag_weight=1.0, quality_weight=0.0
        )
        candidate = _candidate(score=0.0, metadata={"tags": ["running", "red", "blue"]})

        result = scorer.score(target_metadata={"tags": ["running", "red"]}, candidate=candidate)

        # shared={running,red} (2), union={running,red,blue} (3) -> 2/3.
        assert result.final_score == pytest.approx(2 / 3)


class TestPoorQualityProducts:
    def test_a_low_quality_candidate_drags_down_the_final_score(self) -> None:
        scorer = _scorer(
            similarity_weight=0.0, attribute_weight=0.0, tag_weight=0.0, quality_weight=1.0
        )
        candidate = _candidate(score=1.0, metadata={"quality_score": 0.1})

        result = scorer.score(target_metadata={}, candidate=candidate)

        assert result.quality_score == pytest.approx(0.1)
        assert result.final_score == pytest.approx(0.1)

    def test_a_missing_quality_score_defaults_to_zero(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={})

        result = scorer.score(target_metadata={}, candidate=candidate)

        assert result.quality_score == 0.0


class TestSignalShape:
    def test_out_of_range_candidate_score_is_clamped(self) -> None:
        scorer = _scorer()
        candidate = _candidate(score=1.5)

        result = scorer.score(target_metadata={}, candidate=candidate)

        assert result.similarity_score == 1.0

    def test_final_score_is_never_above_one(self) -> None:
        scorer = RecommendationScorer(
            similarity_weight=1.0, attribute_weight=1.0, tag_weight=1.0, quality_weight=1.0
        )
        candidate = _candidate(
            score=1.0,
            metadata={
                "color": "Red",
                "tags": ["a"],
                "quality_score": 1.0,
            },
        )

        result = scorer.score(target_metadata={"color": "Red", "tags": ["a"]}, candidate=candidate)

        assert result.final_score <= 1.0

    def test_uses_configured_default_weights_when_none_are_given(self) -> None:
        scorer = RecommendationScorer()
        candidate = _candidate(score=1.0)

        result = scorer.score(target_metadata={}, candidate=candidate)

        # default similarity_weight=0.55, everything else zero-contribution here.
        assert result.final_score == pytest.approx(0.55)
