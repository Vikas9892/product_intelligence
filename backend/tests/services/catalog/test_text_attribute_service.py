"""Unit tests for `TextAttributeExtractionService`.

Every test asserts on plain input/output — no mocking, since this
service is entirely deterministic (regex + lookup dictionaries), not a
model call.
"""

from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_tags import Source
from app.services.catalog.text_attribute_service import TextAttributeExtractionService


def _by_attribute(predictions: list[AttributePrediction], attribute: str) -> str | None:
    return next((p.value for p in predictions if p.attribute == attribute), None)


class TestExtractAttributes:
    def test_the_phase_worked_example(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Nike Air Zoom Pegasus",
            brand=None,
            category=None,
            description="Lightweight breathable red running shoe with mesh upper",
        )

        assert _by_attribute(predictions, "brand") == "Nike"
        assert _by_attribute(predictions, "category") == "Running Shoes"
        assert _by_attribute(predictions, "color") == "Red"
        assert _by_attribute(predictions, "material") == "Mesh"
        assert _by_attribute(predictions, "style") == "Running"
        # No gender keyword appears anywhere in this example's text.
        assert _by_attribute(predictions, "gender") is None

    def test_trusts_an_already_submitted_brand_at_full_confidence(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Widget", brand="Acme", category=None, description=None
        )

        brand_prediction = next(p for p in predictions if p.attribute == "brand")
        assert brand_prediction.value == "Acme"
        assert brand_prediction.confidence == 1.0
        assert brand_prediction.source is Source.TEXT

    def test_trusts_an_already_submitted_category_at_full_confidence(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Widget", brand=None, category="Outdoor Gear", description=None
        )

        category_prediction = next(p for p in predictions if p.attribute == "category")
        assert category_prediction.value == "Outdoor Gear"
        assert category_prediction.confidence == 1.0

    def test_missing_description_still_extracts_from_name(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Nike Red Running Shoe", brand=None, category=None, description=None
        )

        assert _by_attribute(predictions, "brand") == "Nike"
        assert _by_attribute(predictions, "color") == "Red"

    def test_no_description_and_no_recognizable_name_yields_no_predictions(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Widget", brand=None, category=None, description=None
        )

        assert predictions == []

    def test_unknown_brand_is_not_hallucinated(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Zorbex Blue Widget", brand=None, category=None, description=None
        )

        assert _by_attribute(predictions, "brand") is None
        assert _by_attribute(predictions, "color") == "Blue"

    def test_multiple_colors_picks_the_first_occurring(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Widget",
            brand=None,
            category=None,
            description="A blue and red striped scarf",
        )

        assert _by_attribute(predictions, "color") == "Blue"

    def test_is_case_insensitive(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="NIKE RED WIDGET", brand=None, category=None, description=None
        )

        assert _by_attribute(predictions, "brand") == "Nike"
        assert _by_attribute(predictions, "color") == "Red"

    def test_does_not_match_a_keyword_as_a_substring_of_another_word(self) -> None:
        service = TextAttributeExtractionService()

        # "reddish" contains "red" as a substring but isn't the color red;
        # word-boundary matching must not fire here.
        predictions = service.extract_attributes(
            name="Widget", brand=None, category=None, description="a reddish tint"
        )

        assert _by_attribute(predictions, "color") is None

    def test_malformed_text_does_not_raise(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Widget",
            brand=None,
            category=None,
            description="!!! <<>> \x00\x01 %%%## ??? ---",
        )

        assert predictions == []

    def test_gender_keyword_is_detected(self) -> None:
        service = TextAttributeExtractionService()

        predictions = service.extract_attributes(
            name="Women's Running Jacket", brand=None, category=None, description=None
        )

        assert _by_attribute(predictions, "gender") == "Women"


class TestGenerateTags:
    def test_the_phase_worked_example_includes_the_expected_tags(self) -> None:
        service = TextAttributeExtractionService()

        tags = service.generate_tags(
            name="Nike Air Zoom Pegasus",
            brand=None,
            category=None,
            description="Lightweight breathable red running shoe with mesh upper",
        )

        tag_values = {tag.tag for tag in tags}
        assert "nike" in tag_values
        assert "red" in tag_values
        assert "mesh" in tag_values
        assert "running" in tag_values
        assert "lightweight" in tag_values
        assert "breathable" in tag_values

    def test_tags_have_no_duplicates(self) -> None:
        service = TextAttributeExtractionService()

        tags = service.generate_tags(
            name="Red Widget",
            brand=None,
            category=None,
            description="A red red red widget",
        )

        tag_values = [tag.tag for tag in tags]
        assert len(tag_values) == len(set(tag_values))

    def test_includes_every_matching_color_not_just_the_first(self) -> None:
        service = TextAttributeExtractionService()

        tags = service.generate_tags(
            name="Widget",
            brand=None,
            category=None,
            description="A blue and red striped scarf",
        )

        tag_values = {tag.tag for tag in tags}
        assert "blue" in tag_values
        assert "red" in tag_values

    def test_returns_an_empty_list_for_unrecognizable_text(self) -> None:
        service = TextAttributeExtractionService()

        tags = service.generate_tags(name="Widget", brand=None, category=None, description=None)

        assert tags == []

    def test_every_tag_has_a_valid_confidence_and_source(self) -> None:
        service = TextAttributeExtractionService()

        tags = service.generate_tags(
            name="Nike Red Widget",
            brand=None,
            category=None,
            description="A lightweight cotton item",
        )

        for tag in tags:
            assert 0.0 <= tag.confidence <= 1.0
            assert tag.source is Source.TEXT
