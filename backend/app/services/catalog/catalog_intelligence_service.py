"""Catalog intelligence orchestrator (Phase 7).

`CatalogIntelligenceService.enrich` runs `TextAttributeExtractionService`
and `ImageAttributeExtractionService` (each independently, each already
tested in isolation), merges their `AttributePrediction`s into one
resolved `ProductAttributes`, merges and deduplicates their `CatalogTag`s,
and computes a quality score — bundling all of it into a
`CatalogIntelligenceResult`. Kept as a thin orchestrator, the same way
`HybridSearchService` is: no extraction logic of its own, only merge/
conflict-resolution/scoring.

**Conflict resolution.** Both extraction services can propose a value for
the same attribute (in practice, only `color` — image analysis never
attempts brand/category/gender/etc.). Grouped by attribute name, the
candidate with the *highest confidence* wins; if every candidate for an
attribute agrees on the same value, that agreement is logged (informally,
a "hybrid" confirmation) even though `ProductAttributes` itself has no
per-field source to record it in. A winning candidate whose confidence
falls below `CatalogIntelligenceSettings.attribute_confidence_threshold`
is dropped entirely — that attribute stays `None` rather than being
filled with a low-confidence guess.

**Tag merging** is similar but not identical: tags aren't constrained to
one value per attribute, so merging is really deduplication (by tag
string) plus a `Source.HYBRID` upgrade when the same tag string was
proposed by *both* extraction services, then a confidence-descending sort
and a cap at `CatalogIntelligenceSettings.max_generated_tags`.

**Quality score** is a configurable weighted sum of three signals:

    quality = completeness_weight * completeness
            + confidence_weight    * confidence
            + consistency_weight   * consistency

- `completeness` — the fraction of `ProductAttributes`' fields (excluding
  its own aggregate `confidence`) that got filled.
- `confidence` — the mean confidence across every attribute that *was*
  filled (0 if none were).
- `consistency` — `1 - (conflicting attributes / attributes with any
  candidate)`; an attribute only counts as "conflicting" if multiple
  candidates for it disagreed on the value.

The result is clamped to `[0, 1]` — the weights aren't required to sum to
exactly 1.0 (an operator could reasonably want to tune only one of them),
so an unusual combination can't be allowed to push the score itself
outside its own valid range.
"""

import time
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import CatalogIntelligenceException
from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.catalog_tags import CatalogTag, Source
from app.models.product_attributes import ProductAttributes
from app.services.catalog.image_attribute_service import ImageAttributeExtractionService
from app.services.catalog.text_attribute_service import TextAttributeExtractionService

logger = get_logger(__name__)

#: Every `ProductAttributes` field a merged attribute value can be
#: written to — i.e. everything except its own aggregate `confidence`.
_ATTRIBUTE_FIELD_NAMES: tuple[str, ...] = tuple(
    name for name in ProductAttributes.model_fields if name != "confidence"
)


class CatalogIntelligenceService:
    """Orchestrates text + image attribute extraction, conflict resolution, and scoring."""

    def __init__(
        self,
        *,
        text_attribute_service: TextAttributeExtractionService | None = None,
        image_attribute_service: ImageAttributeExtractionService | None = None,
        enable_text_attributes: bool | None = None,
        enable_image_attributes: bool | None = None,
        confidence_threshold: float | None = None,
        max_tags: int | None = None,
        completeness_weight: float | None = None,
        confidence_weight: float | None = None,
        consistency_weight: float | None = None,
    ) -> None:
        self._text_attribute_service = (
            text_attribute_service
            if text_attribute_service is not None
            else TextAttributeExtractionService()
        )
        self._image_attribute_service = (
            image_attribute_service
            if image_attribute_service is not None
            else ImageAttributeExtractionService()
        )
        self._enable_text_attributes = (
            enable_text_attributes
            if enable_text_attributes is not None
            else settings.catalog_intelligence.enable_text_attributes
        )
        self._enable_image_attributes = (
            enable_image_attributes
            if enable_image_attributes is not None
            else settings.catalog_intelligence.enable_image_attributes
        )
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.catalog_intelligence.attribute_confidence_threshold
        )
        self._max_tags = (
            max_tags if max_tags is not None else settings.catalog_intelligence.max_generated_tags
        )
        self._completeness_weight = (
            completeness_weight
            if completeness_weight is not None
            else settings.catalog_intelligence.quality_completeness_weight
        )
        self._confidence_weight = (
            confidence_weight
            if confidence_weight is not None
            else settings.catalog_intelligence.quality_confidence_weight
        )
        self._consistency_weight = (
            consistency_weight
            if consistency_weight is not None
            else settings.catalog_intelligence.quality_consistency_weight
        )

    async def enrich(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image_path: Path,
    ) -> CatalogIntelligenceResult:
        """Extract, merge, and score catalog attributes/tags for one product.

        `image_path` should be the already-*processed* (standardized)
        image — the same one `CLIPEmbeddingService` embeds from, not the
        raw upload. Raises whatever `ImageAttributeExtractionService`
        raises for a corrupt/unreadable image, or
        `CatalogIntelligenceException` if merging/scoring the otherwise
        successfully-extracted predictions fails unexpectedly.
        """
        start = time.monotonic()

        text_predictions: list[AttributePrediction] = []
        text_tags: list[CatalogTag] = []
        if self._enable_text_attributes:
            text_predictions = self._text_attribute_service.extract_attributes(
                name=name, brand=brand, category=category, description=description
            )
            text_tags = self._text_attribute_service.generate_tags(
                name=name, brand=brand, category=category, description=description
            )

        image_predictions: list[AttributePrediction] = []
        image_tags: list[CatalogTag] = []
        if self._enable_image_attributes:
            image_predictions = await self._image_attribute_service.extract_attributes(image_path)
            image_tags = await self._image_attribute_service.generate_tags(image_path)

        try:
            attributes, conflict_count, considered_count = self._merge_attributes(
                text_predictions + image_predictions
            )
            tags = self._merge_tags(text_tags + image_tags)
            quality_score = self._compute_quality_score(
                attributes, conflict_count, considered_count
            )
        except Exception as exc:
            raise CatalogIntelligenceException(
                "Failed to merge extracted attributes and tags."
            ) from exc

        processing_time = time.monotonic() - start
        filled_count = sum(
            1
            for field_name in _ATTRIBUTE_FIELD_NAMES
            if getattr(attributes, field_name) is not None
        )
        logger.info(
            "Catalog intelligence complete: attributes_filled=%d/%d, tags=%d, "
            "quality_score=%.2f, conflicts=%d, processing_time=%.4fs",
            filled_count,
            len(_ATTRIBUTE_FIELD_NAMES),
            len(tags),
            quality_score,
            conflict_count,
            processing_time,
        )

        return CatalogIntelligenceResult(
            attributes=attributes,
            tags=tags,
            quality_score=quality_score,
            processing_time=processing_time,
        )

    def _merge_attributes(
        self, predictions: list[AttributePrediction]
    ) -> tuple[ProductAttributes, int, int]:
        """Resolve `predictions` into one `ProductAttributes`, higher confidence wins.

        Returns `(attributes, conflict_count, considered_count)` — the
        latter two feed `_compute_quality_score`'s consistency term.
        """
        by_attribute: dict[str, list[AttributePrediction]] = {}
        for prediction in predictions:
            by_attribute.setdefault(prediction.attribute, []).append(prediction)

        resolved: dict[str, str] = {}
        winning_confidences: list[float] = []
        conflict_count = 0

        for attribute, candidates in by_attribute.items():
            best = max(candidates, key=lambda candidate: candidate.confidence)
            distinct_values = {candidate.value for candidate in candidates}

            if len(distinct_values) > 1:
                conflict_count += 1
                logger.info(
                    "Attribute conflict resolved for '%s': winner=%r (confidence=%.2f) among %d candidate(s)",
                    attribute,
                    best.value,
                    best.confidence,
                    len(candidates),
                )
            elif len(candidates) > 1:
                logger.info(
                    "Attribute agreement for '%s': value=%r confirmed by %d sources",
                    attribute,
                    best.value,
                    len(candidates),
                )

            if best.confidence < self._confidence_threshold:
                continue
            resolved[attribute] = best.value
            winning_confidences.append(best.confidence)

        aggregate_confidence = (
            sum(winning_confidences) / len(winning_confidences) if winning_confidences else 0.0
        )
        attributes = ProductAttributes(confidence=aggregate_confidence, **resolved)
        return attributes, conflict_count, len(by_attribute)

    def _merge_tags(self, tags: list[CatalogTag]) -> list[CatalogTag]:
        """Deduplicate `tags` by string, upgrading agreeing sources to `Source.HYBRID`."""
        grouped: dict[str, list[CatalogTag]] = {}
        for tag in tags:
            key = tag.tag.strip().lower()
            if not key:
                continue
            grouped.setdefault(key, []).append(tag)

        merged: list[CatalogTag] = []
        for key, candidates in grouped.items():
            best_confidence = max(candidate.confidence for candidate in candidates)
            if best_confidence < self._confidence_threshold:
                continue
            sources = {candidate.source for candidate in candidates}
            source = Source.HYBRID if len(sources) > 1 else next(iter(sources))
            merged.append(CatalogTag(tag=key, confidence=best_confidence, source=source))

        merged.sort(key=lambda tag: tag.confidence, reverse=True)
        return merged[: self._max_tags]

    def _compute_quality_score(
        self, attributes: ProductAttributes, conflict_count: int, considered_count: int
    ) -> float:
        filled_count = sum(
            1
            for field_name in _ATTRIBUTE_FIELD_NAMES
            if getattr(attributes, field_name) is not None
        )
        completeness = filled_count / len(_ATTRIBUTE_FIELD_NAMES)
        confidence = attributes.confidence
        consistency = 1.0 - (conflict_count / considered_count) if considered_count else 1.0

        score = (
            self._completeness_weight * completeness
            + self._confidence_weight * confidence
            + self._consistency_weight * consistency
        )
        return max(0.0, min(1.0, score))
