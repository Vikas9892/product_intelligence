"""Unit tests for `SimilarityScorer`."""

from uuid import uuid4

import pytest

from app.models.product_attributes import ProductAttributes
from app.models.search import HybridSearchResult, SearchModality
from app.services.duplicate.similarity_scorer import SimilarityScorer


def _candidate(
    *,
    image_score: float = 0.9,
    text_score: float = 0.9,
    metadata: dict[str, object] | None = None,
) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=uuid4(),
        score=image_score,
        image_score=image_score,
        text_score=text_score,
        metadata=metadata if metadata is not None else {},
        matched_modalities=[SearchModality.IMAGE, SearchModality.TEXT],
    )


def _scorer(
    *,
    image_weight: float = 0.35,
    text_weight: float = 0.25,
    metadata_weight: float = 0.20,
    attribute_weight: float = 0.20,
) -> SimilarityScorer:
    return SimilarityScorer(
        image_weight=image_weight,
        text_weight=text_weight,
        metadata_weight=metadata_weight,
        attribute_weight=attribute_weight,
    )


class TestSignalShape:
    def test_returns_exactly_four_named_signals(self) -> None:
        scorer = _scorer()
        candidate = _candidate()

        result = scorer.score(
            name="Widget",
            brand="Nike",
            category="Shoes",
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        assert {signal.name for signal in result.signals} == {
            "image",
            "text",
            "metadata",
            "attribute",
        }
        assert result.product_id == candidate.product_id

    def test_contribution_equals_score_times_weight(self) -> None:
        scorer = _scorer(
            image_weight=0.5, text_weight=0.0, metadata_weight=0.0, attribute_weight=0.5
        )
        candidate = _candidate(image_score=0.8, text_score=0.0)

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        image_signal = next(s for s in result.signals if s.name == "image")
        assert image_signal.score == 0.8
        assert image_signal.weight == 0.5
        assert image_signal.contribution == pytest.approx(0.4)

    def test_out_of_range_candidate_scores_are_clamped(self) -> None:
        scorer = _scorer()
        candidate = _candidate(image_score=1.2, text_score=-0.3)

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        image_signal = next(s for s in result.signals if s.name == "image")
        text_signal = next(s for s in result.signals if s.name == "text")
        assert image_signal.score == 1.0
        assert text_signal.score == 0.0


class TestIdenticalProducts:
    def test_identical_metadata_and_attributes_score_near_one(self) -> None:
        scorer = _scorer()
        candidate = _candidate(
            image_score=1.0,
            text_score=1.0,
            metadata={
                "name": "Nike Air Zoom Pegasus",
                "brand": "Nike",
                "category": "running-shoes",
                "color": "Red",
                "material": "Mesh",
                "gender": "Men",
                "style": "Running",
            },
        )
        attributes = ProductAttributes(
            brand="Nike",
            category="Running Shoes",
            color="Red",
            material="Mesh",
            gender="Men",
            style="Running",
        )

        result = scorer.score(
            name="Nike Air Zoom Pegasus",
            brand="Nike",
            category="Running Shoes",
            attributes=attributes,
            candidate=candidate,
        )

        assert result.overall_similarity > 0.95


class TestTyposAndFormatting:
    def test_a_typo_in_brand_still_scores_highly_but_not_perfectly(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"name": "Nike Widget", "brand": "Nikee"})

        result = scorer.score(
            name="Nike Widget",
            brand="Nike",
            category=None,
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        metadata_signal = next(s for s in result.signals if s.name == "metadata")
        assert 0.7 < metadata_signal.score < 1.0

    def test_a_slugified_category_still_matches_its_natural_language_form(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"category": "running-shoes"})

        result = scorer.score(
            name="Widget",
            brand=None,
            category="Running Shoes",
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        metadata_signal = next(s for s in result.signals if s.name == "metadata")
        assert metadata_signal.score > 0.85


class TestMissingValues:
    def test_a_field_missing_on_the_candidate_is_excluded_not_penalized(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"color": "Red"})
        attributes = ProductAttributes(color="Red", material="Mesh")

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=attributes,
            candidate=candidate,
        )

        attribute_signal = next(s for s in result.signals if s.name == "attribute")
        assert attribute_signal.score == 1.0

    def test_no_overlapping_fields_yields_a_zero_attribute_signal(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={})

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        attribute_signal = next(s for s in result.signals if s.name == "attribute")
        metadata_signal = next(s for s in result.signals if s.name == "metadata")
        assert attribute_signal.score == 0.0
        assert metadata_signal.score == 0.0


class TestConflictingAttributes:
    def test_a_conflicting_color_drags_down_the_attribute_signal(self) -> None:
        scorer = _scorer()
        candidate = _candidate(metadata={"color": "Blue", "material": "Mesh"})
        attributes = ProductAttributes(color="Red", material="Mesh")

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=attributes,
            candidate=candidate,
        )

        attribute_signal = next(s for s in result.signals if s.name == "attribute")
        # color disagrees (low fuzzy ratio), material agrees (1.0) -> averages well below a full match.
        assert attribute_signal.score < 0.7


class TestConstructorDefaults:
    def test_uses_configured_default_weights_when_none_are_given(self) -> None:
        scorer = SimilarityScorer()
        candidate = _candidate(image_score=1.0, text_score=1.0)

        result = scorer.score(
            name="Widget",
            brand=None,
            category=None,
            attributes=ProductAttributes(),
            candidate=candidate,
        )

        image_signal = next(s for s in result.signals if s.name == "image")
        assert image_signal.weight == pytest.approx(0.35)
