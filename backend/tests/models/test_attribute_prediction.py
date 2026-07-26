"""Unit tests for `AttributePrediction`."""

import pytest
from pydantic import ValidationError

from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_tags import Source


class TestAttributePrediction:
    def test_constructs_with_all_fields(self) -> None:
        prediction = AttributePrediction(
            attribute="color", value="red", confidence=0.95, source=Source.TEXT
        )

        assert prediction.attribute == "color"
        assert prediction.value == "red"
        assert prediction.confidence == 0.95
        assert prediction.source is Source.TEXT

    def test_rejects_a_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            AttributePrediction(attribute="color", value="red", confidence=1.5, source=Source.TEXT)

    def test_rejects_a_negative_confidence(self) -> None:
        with pytest.raises(ValidationError):
            AttributePrediction(attribute="color", value="red", confidence=-0.5, source=Source.TEXT)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        prediction = AttributePrediction(
            attribute="brand", value="Nike", confidence=0.9, source=Source.HYBRID
        )

        dumped = prediction.model_dump(mode="json")
        restored = AttributePrediction.model_validate(dumped)

        assert restored == prediction
