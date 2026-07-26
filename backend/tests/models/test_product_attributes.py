"""Unit tests for `ProductAttributes`."""

import pytest
from pydantic import ValidationError

from app.models.product_attributes import ProductAttributes


class TestProductAttributes:
    def test_all_fields_are_optional(self) -> None:
        attributes = ProductAttributes()

        assert attributes.brand is None
        assert attributes.category is None
        assert attributes.subcategory is None
        assert attributes.color is None
        assert attributes.material is None
        assert attributes.pattern is None
        assert attributes.gender is None
        assert attributes.age_group is None
        assert attributes.style is None
        assert attributes.season is None
        assert attributes.occasion is None

    def test_confidence_defaults_to_zero(self) -> None:
        attributes = ProductAttributes()

        assert attributes.confidence == 0.0

    def test_constructs_with_all_fields(self) -> None:
        attributes = ProductAttributes(
            brand="Nike",
            category="Running Shoes",
            subcategory="Trail Running",
            color="Red",
            material="Mesh",
            pattern="Solid",
            gender="Men",
            age_group="Adult",
            style="Running",
            season="Summer",
            occasion="Sports",
            confidence=0.87,
        )

        assert attributes.brand == "Nike"
        assert attributes.category == "Running Shoes"
        assert attributes.subcategory == "Trail Running"
        assert attributes.color == "Red"
        assert attributes.material == "Mesh"
        assert attributes.pattern == "Solid"
        assert attributes.gender == "Men"
        assert attributes.age_group == "Adult"
        assert attributes.style == "Running"
        assert attributes.season == "Summer"
        assert attributes.occasion == "Sports"
        assert attributes.confidence == 0.87

    def test_rejects_a_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            ProductAttributes(confidence=1.1)

    def test_rejects_a_negative_confidence(self) -> None:
        with pytest.raises(ValidationError):
            ProductAttributes(confidence=-0.1)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        attributes = ProductAttributes(brand="Nike", color="Red", confidence=0.8)

        dumped = attributes.model_dump(mode="json")
        restored = ProductAttributes.model_validate(dumped)

        assert restored == attributes
