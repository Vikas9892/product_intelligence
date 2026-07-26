"""Unit tests for `CatalogTag` and `Source`."""

import pytest
from pydantic import ValidationError

from app.models.catalog_tags import CatalogTag, Source


class TestSource:
    def test_has_the_three_expected_values(self) -> None:
        assert Source.TEXT.value == "text"
        assert Source.IMAGE.value == "image"
        assert Source.HYBRID.value == "hybrid"


class TestCatalogTag:
    def test_constructs_with_all_fields(self) -> None:
        tag = CatalogTag(tag="running", confidence=0.9, source=Source.TEXT)

        assert tag.tag == "running"
        assert tag.confidence == 0.9
        assert tag.source is Source.TEXT

    def test_rejects_a_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            CatalogTag(tag="running", confidence=1.1, source=Source.TEXT)

    def test_rejects_a_negative_confidence(self) -> None:
        with pytest.raises(ValidationError):
            CatalogTag(tag="running", confidence=-0.1, source=Source.TEXT)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        tag = CatalogTag(tag="mesh", confidence=0.75, source=Source.IMAGE)

        dumped = tag.model_dump(mode="json")
        restored = CatalogTag.model_validate(dumped)

        assert restored == tag
