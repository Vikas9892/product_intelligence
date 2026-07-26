"""Deterministic, pixel-analysis-based image attribute extraction (Phase 7).

`ImageAttributeExtractionService` finds catalog attributes and tags by
analyzing an already-*processed* product image (the standardized JPEG
`ImageProcessingService`, Phase 3, produced — the same `processed_path`
`CLIPEmbeddingService` already embeds from) using plain Pillow pixel
statistics: dominant color, brightness, orientation, aspect ratio, and a
resolution bucket. No new ML model, no object detection, no OCR —
deliberately out of this phase's scope.

Mirrors `TextAttributeExtractionService`'s two-method shape
(`extract_attributes`/`generate_tags`) so `CatalogIntelligenceService`
calls both extraction services identically, even though only `color` maps
to an actual `ProductAttributes` field — brightness/orientation/aspect
ratio/resolution have no corresponding attribute, so they only ever
become tags. Unlike the text service, every method here *is* `async def`
and runs its Pillow work inside `run_in_threadpool`, matching
`ImageProcessingService`'s own established pattern for exactly the same
reason: decoding an image and scanning its pixels is blocking, CPU-bound
work.
"""

from pathlib import Path

from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.exceptions.errors import CatalogIntelligenceException
from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_tags import CatalogTag, Source
from app.utils.image import (
    classify_brightness,
    classify_color_name,
    classify_orientation,
    classify_resolution,
    compute_brightness,
    compute_dominant_color,
)

logger = get_logger(__name__)

# Confidence assigned to pixel-derived signals — fixed and deterministic,
# the same "not learned or tuned" reasoning
# `TextAttributeExtractionService`'s confidence constants document. Color
# gets one confidence whether it's read as an attribute or a tag, since
# it's the exact same underlying signal either way.
_COLOR_CONFIDENCE = 0.7
_TAG_CONFIDENCE = 0.7


class ImageAttributeExtractionService:
    """Extracts catalog attributes and tags from an already-processed product image."""

    async def extract_attributes(self, image_path: Path) -> list[AttributePrediction]:
        """Return attribute predictions derivable from pixel analysis alone.

        Only `color` today — brightness/orientation/aspect ratio/
        resolution have no corresponding `ProductAttributes` field; those
        become tags instead (see `generate_tags`).
        """
        color_name = await run_in_threadpool(self._analyze_color, image_path)
        return [
            AttributePrediction(
                attribute="color",
                value=color_name.capitalize(),
                confidence=_COLOR_CONFIDENCE,
                source=Source.IMAGE,
            )
        ]

    async def generate_tags(self, image_path: Path) -> list[CatalogTag]:
        """Return orientation/brightness/resolution/color tags for the image at `image_path`."""
        tags = await run_in_threadpool(self._analyze_tags, image_path)
        logger.info("Image tag generation complete: tags=%d", len(tags))
        return tags

    def _analyze_color(self, image_path: Path) -> str:
        try:
            with Image.open(image_path) as opened:
                rgb = compute_dominant_color(opened)
        except Exception as exc:
            raise CatalogIntelligenceException(
                "Failed to analyze the image's dominant color."
            ) from exc
        return classify_color_name(rgb)

    def _analyze_tags(self, image_path: Path) -> list[CatalogTag]:
        try:
            with Image.open(image_path) as opened:
                width, height = opened.size
                rgb = compute_dominant_color(opened)
                brightness = compute_brightness(opened)
        except Exception as exc:
            raise CatalogIntelligenceException(
                "Failed to analyze the image for tag generation."
            ) from exc

        return [
            CatalogTag(
                tag=classify_orientation(width, height),
                confidence=_TAG_CONFIDENCE,
                source=Source.IMAGE,
            ),
            CatalogTag(
                tag=classify_brightness(brightness), confidence=_TAG_CONFIDENCE, source=Source.IMAGE
            ),
            CatalogTag(
                tag=classify_resolution(width, height),
                confidence=_TAG_CONFIDENCE,
                source=Source.IMAGE,
            ),
            CatalogTag(
                tag=classify_color_name(rgb), confidence=_COLOR_CONFIDENCE, source=Source.IMAGE
            ),
        ]
