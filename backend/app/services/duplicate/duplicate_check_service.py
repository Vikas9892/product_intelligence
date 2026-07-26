"""`DuplicateCheckService`: powers `POST /products/check-duplicate` (Phase 8 Milestone 5).

Answers "would this be a duplicate?" for a caller who never intends to
actually upload the product — it never persists anything, unlike
`ProductService.process_upload`. Composes the same two services that
step needs (`CatalogIntelligenceService`, for the `ProductAttributes`
`DuplicateDetectionService.detect` requires; `DuplicateDetectionService`
itself), plus `ImageProcessingService` directly (needed only to produce
the *processed* image path catalog intelligence's image attribute
extraction reads from — the same image
`DuplicateDetectionService`/`HybridSearchService` will independently
re-process again for embedding, mirroring the accepted redundancy already
documented in `ProductService`'s own docstring for the same reason).

Kept as its own thin service (not new logic bolted onto
`DuplicateDetectionService` or `ProductService`) so the router stays a
one-call adapter, matching the "thin routers, service owns the sequence"
convention `ProductService`/`HybridSearchService` already established.
"""

from pathlib import Path

from app.core.config import settings
from app.models.duplicate_decision import DuplicateDecision
from app.schemas.product import ProductImage
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.image_processing_service import ImageProcessingService


class DuplicateCheckService:
    """Orchestrates catalog intelligence + duplicate detection for a not-yet-uploaded product."""

    def __init__(
        self,
        *,
        image_processing_service: ImageProcessingService | None = None,
        catalog_intelligence_service: CatalogIntelligenceService | None = None,
        duplicate_detection_service: DuplicateDetectionService | None = None,
        upload_dir: Path | None = None,
    ) -> None:
        self._image_processing_service = (
            image_processing_service
            if image_processing_service is not None
            else ImageProcessingService()
        )
        self._catalog_intelligence_service = (
            catalog_intelligence_service
            if catalog_intelligence_service is not None
            else CatalogIntelligenceService()
        )
        self._duplicate_detection_service = (
            duplicate_detection_service
            if duplicate_detection_service is not None
            else DuplicateDetectionService()
        )
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir

    async def check(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image: ProductImage,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> DuplicateDecision:
        """Check whether a product described by `image`/metadata looks like a duplicate.

        `image` must describe a file `UploadService` has already written
        under this service's `upload_dir` — the same contract
        `ProductService.process_upload` has. Raises whatever
        `ImageProcessingService`/`CatalogIntelligenceService`/
        `DuplicateDetectionService` raise for their own failure modes.
        """
        stored_path = self._upload_dir / image.stored_filename
        image_metadata = await self._image_processing_service.process_image(
            stored_path, image.stored_filename
        )
        catalog_result = await self._catalog_intelligence_service.enrich(
            name=name,
            brand=brand,
            category=category,
            description=description,
            image_path=image_metadata.processed_path,
        )
        return await self._duplicate_detection_service.detect(
            name=name,
            brand=brand,
            category=category,
            description=description,
            attributes=catalog_result.attributes,
            image=image,
            top_k=top_k,
            threshold=threshold,
        )
