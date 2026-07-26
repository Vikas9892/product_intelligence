"""Unit tests for `CatalogIntelligenceService`.

Composes fake `TextAttributeExtractionService`/`ImageAttributeExtractionService`
doubles (not the real deterministic pipelines — those are already
covered by `test_text_attribute_service.py`/`test_image_attribute_service.py`)
so the merge/conflict-resolution/quality-score logic can be tested
against precisely controlled inputs.
"""

from pathlib import Path

import pytest

from app.exceptions.errors import CatalogIntelligenceException
from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.catalog_tags import CatalogTag, Source
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.catalog.image_attribute_service import ImageAttributeExtractionService
from app.services.catalog.text_attribute_service import TextAttributeExtractionService


class _FakeTextAttributeService(TextAttributeExtractionService):
    def __init__(
        self,
        *,
        predictions: list[AttributePrediction] | None = None,
        tags: list[CatalogTag] | None = None,
    ) -> None:
        self._predictions = predictions if predictions is not None else []
        self._tags = tags if tags is not None else []

    def extract_attributes(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
    ) -> list[AttributePrediction]:
        return self._predictions

    def generate_tags(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
    ) -> list[CatalogTag]:
        return self._tags


class _FakeImageAttributeService(ImageAttributeExtractionService):
    def __init__(
        self,
        *,
        predictions: list[AttributePrediction] | None = None,
        tags: list[CatalogTag] | None = None,
    ) -> None:
        self._predictions = predictions if predictions is not None else []
        self._tags = tags if tags is not None else []

    async def extract_attributes(self, image_path: Path) -> list[AttributePrediction]:
        return self._predictions

    async def generate_tags(self, image_path: Path) -> list[CatalogTag]:
        return self._tags


def _build_service(
    *,
    text_predictions: list[AttributePrediction] | None = None,
    text_tags: list[CatalogTag] | None = None,
    image_predictions: list[AttributePrediction] | None = None,
    image_tags: list[CatalogTag] | None = None,
    confidence_threshold: float = 0.60,
    max_tags: int = 20,
    completeness_weight: float = 0.50,
    confidence_weight: float = 0.30,
    consistency_weight: float = 0.20,
    enable_text_attributes: bool = True,
    enable_image_attributes: bool = True,
) -> CatalogIntelligenceService:
    return CatalogIntelligenceService(
        text_attribute_service=_FakeTextAttributeService(
            predictions=text_predictions, tags=text_tags
        ),
        image_attribute_service=_FakeImageAttributeService(
            predictions=image_predictions, tags=image_tags
        ),
        confidence_threshold=confidence_threshold,
        max_tags=max_tags,
        completeness_weight=completeness_weight,
        confidence_weight=confidence_weight,
        consistency_weight=consistency_weight,
        enable_text_attributes=enable_text_attributes,
        enable_image_attributes=enable_image_attributes,
    )


async def _enrich(service: CatalogIntelligenceService, tmp_path: Path) -> CatalogIntelligenceResult:
    return await service.enrich(
        name="Widget", brand=None, category=None, description=None, image_path=tmp_path / "x.jpg"
    )


class TestConflictResolution:
    async def test_higher_confidence_wins_the_phase_worked_example(self, tmp_path: Path) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=0.95, source=Source.TEXT
                )
            ],
            image_predictions=[
                AttributePrediction(
                    attribute="color", value="Orange", confidence=0.61, source=Source.IMAGE
                )
            ],
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.color == "Red"

    async def test_agreement_between_sources_still_fills_the_attribute(
        self, tmp_path: Path
    ) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=0.8, source=Source.TEXT
                )
            ],
            image_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=0.7, source=Source.IMAGE
                )
            ],
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.color == "Red"

    async def test_a_below_threshold_winner_leaves_the_attribute_unset(
        self, tmp_path: Path
    ) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=0.5, source=Source.TEXT
                )
            ],
            confidence_threshold=0.60,
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.color is None

    async def test_only_one_side_proposing_a_value_still_fills_it(self, tmp_path: Path) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="brand", value="Nike", confidence=0.9, source=Source.TEXT
                )
            ]
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.brand == "Nike"


class TestTagMerging:
    async def test_deduplicates_a_tag_proposed_by_both_sources(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[CatalogTag(tag="red", confidence=0.8, source=Source.TEXT)],
            image_tags=[CatalogTag(tag="red", confidence=0.7, source=Source.IMAGE)],
        )

        result = await _enrich(service, tmp_path)

        assert len(result.tags) == 1

    async def test_a_tag_from_both_sources_becomes_hybrid(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[CatalogTag(tag="red", confidence=0.8, source=Source.TEXT)],
            image_tags=[CatalogTag(tag="red", confidence=0.7, source=Source.IMAGE)],
        )

        result = await _enrich(service, tmp_path)

        assert result.tags[0].source is Source.HYBRID

    async def test_a_single_source_tag_keeps_its_own_source(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[CatalogTag(tag="nike", confidence=0.9, source=Source.TEXT)]
        )

        result = await _enrich(service, tmp_path)

        assert result.tags[0].source is Source.TEXT

    async def test_a_whitespace_only_tag_is_excluded(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[CatalogTag(tag="   ", confidence=0.9, source=Source.TEXT)]
        )

        result = await _enrich(service, tmp_path)

        assert result.tags == []

    async def test_a_below_threshold_tag_is_excluded(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[CatalogTag(tag="maybe", confidence=0.3, source=Source.TEXT)],
            confidence_threshold=0.60,
        )

        result = await _enrich(service, tmp_path)

        assert result.tags == []

    async def test_caps_tags_at_max_tags_keeping_the_highest_confidence(
        self, tmp_path: Path
    ) -> None:
        tags = [
            CatalogTag(tag=f"tag{i}", confidence=0.6 + i * 0.01, source=Source.TEXT)
            for i in range(10)
        ]
        service = _build_service(text_tags=tags, max_tags=3)

        result = await _enrich(service, tmp_path)

        assert len(result.tags) == 3
        assert result.tags[0].tag == "tag9"

    async def test_tags_are_sorted_by_descending_confidence(self, tmp_path: Path) -> None:
        service = _build_service(
            text_tags=[
                CatalogTag(tag="low", confidence=0.65, source=Source.TEXT),
                CatalogTag(tag="high", confidence=0.95, source=Source.TEXT),
            ]
        )

        result = await _enrich(service, tmp_path)

        assert [tag.tag for tag in result.tags] == ["high", "low"]


class TestQualityScore:
    async def test_no_predictions_yields_the_consistency_only_floor(self, tmp_path: Path) -> None:
        service = _build_service(
            completeness_weight=0.5, confidence_weight=0.3, consistency_weight=0.2
        )

        result = await _enrich(service, tmp_path)

        # completeness=0, confidence=0, consistency=1 (nothing to conflict) -> 0.2
        assert result.quality_score == pytest.approx(0.2)

    async def test_quality_score_reflects_a_conflict(self, tmp_path: Path) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=1.0, source=Source.TEXT
                )
            ],
            image_predictions=[
                AttributePrediction(
                    attribute="color", value="Orange", confidence=0.9, source=Source.IMAGE
                )
            ],
            completeness_weight=0.0,
            confidence_weight=0.0,
            consistency_weight=1.0,
        )

        result = await _enrich(service, tmp_path)

        # One attribute considered, one conflicting -> consistency = 0.
        assert result.quality_score == pytest.approx(0.0)

    async def test_quality_score_is_never_above_one(self, tmp_path: Path) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="brand", value="Nike", confidence=1.0, source=Source.TEXT
                )
            ],
            completeness_weight=1.0,
            confidence_weight=1.0,
            consistency_weight=1.0,
        )

        result = await _enrich(service, tmp_path)

        assert result.quality_score <= 1.0

    async def test_processing_time_is_recorded(self, tmp_path: Path) -> None:
        service = _build_service()

        result = await _enrich(service, tmp_path)

        assert result.processing_time >= 0.0


class TestFeatureFlags:
    async def test_disabling_text_attributes_ignores_text_predictions(self, tmp_path: Path) -> None:
        service = _build_service(
            text_predictions=[
                AttributePrediction(
                    attribute="brand", value="Nike", confidence=0.9, source=Source.TEXT
                )
            ],
            enable_text_attributes=False,
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.brand is None

    async def test_disabling_image_attributes_ignores_image_predictions(
        self, tmp_path: Path
    ) -> None:
        service = _build_service(
            image_predictions=[
                AttributePrediction(
                    attribute="color", value="Red", confidence=0.9, source=Source.IMAGE
                )
            ],
            enable_image_attributes=False,
        )

        result = await _enrich(service, tmp_path)

        assert result.attributes.color is None


class TestErrorWrapping:
    async def test_wraps_an_unexpected_merge_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = _build_service()

        def _broken_merge(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service, "_merge_attributes", _broken_merge)

        with pytest.raises(CatalogIntelligenceException):
            await _enrich(service, tmp_path)
