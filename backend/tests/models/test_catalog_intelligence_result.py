"""Unit tests for `CatalogIntelligenceResult`."""

import pytest
from pydantic import ValidationError

from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.catalog_tags import CatalogTag, Source
from app.models.product_attributes import ProductAttributes


class TestCatalogIntelligenceResult:
    def test_constructs_with_all_fields(self) -> None:
        attributes = ProductAttributes(brand="Nike", confidence=0.9)
        tags = [CatalogTag(tag="running", confidence=0.9, source=Source.TEXT)]

        result = CatalogIntelligenceResult(
            attributes=attributes, tags=tags, quality_score=0.85, processing_time=0.012
        )

        assert result.attributes == attributes
        assert result.tags == tags
        assert result.quality_score == 0.85
        assert result.processing_time == 0.012

    def test_tags_defaults_to_empty_list(self) -> None:
        result = CatalogIntelligenceResult(
            attributes=ProductAttributes(), quality_score=0.0, processing_time=0.0
        )

        assert result.tags == []

    def test_rejects_a_quality_score_above_one(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceResult(
                attributes=ProductAttributes(), quality_score=1.5, processing_time=0.0
            )

    def test_rejects_a_negative_quality_score(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceResult(
                attributes=ProductAttributes(), quality_score=-0.1, processing_time=0.0
            )

    def test_rejects_a_negative_processing_time(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceResult(
                attributes=ProductAttributes(), quality_score=0.5, processing_time=-1.0
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = CatalogIntelligenceResult(
            attributes=ProductAttributes(brand="Nike", confidence=0.9),
            tags=[CatalogTag(tag="running", confidence=0.9, source=Source.TEXT)],
            quality_score=0.85,
            processing_time=0.012,
        )

        dumped = result.model_dump(mode="json")
        restored = CatalogIntelligenceResult.model_validate(dumped)

        assert restored == result
