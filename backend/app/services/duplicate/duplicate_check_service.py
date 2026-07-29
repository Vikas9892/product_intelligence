"""`DuplicateCheckService`: powers `POST /products/check-duplicate` (Phase 8 Milestone 5, extended Phase 15).

Answers "would this be a duplicate?" for a caller who never intends to
actually upload the product — it never persists anything, unlike
`ProductService.process_upload`. Composes `ImageProcessingService`
(needed only to produce the *processed* image path catalog intelligence's
image attribute extraction reads from — the same image
`DuplicateDetectionService`/`DuplicateVerificationService` will
independently re-process again for embedding, mirroring the accepted
redundancy `ProductService`'s own docstring documents) and
`CatalogIntelligenceService` (for the `ProductAttributes` both duplicate
services need).

**Two backends, one return type (Phase 15).** When
`DUPLICATE_VERIFICATION__ENABLED` is off (the default), this delegates to
`DuplicateDetectionService` (weighted similarity, Phase 8) exactly as
before. When on, it delegates to `DuplicateVerificationService`
(cross-encoder + business rules, Phase 15). Either way `check` returns a
`DuplicateVerification` — the weighted path is adapted into that shape
with `cross_encoder_score`/`retrieval_similarity` left `None` — so the
router maps one type regardless, and the richer response fields are
simply absent when verification is off.
"""

from pathlib import Path

from app.core.config import settings
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_verification import DuplicateVerification
from app.models.verification_reason import VerificationReason
from app.schemas.product import ProductImage
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.duplicate.duplicate_verification_service import DuplicateVerificationService
from app.services.image_processing_service import ImageProcessingService


class DuplicateCheckService:
    """Orchestrates catalog intelligence + duplicate detection/verification for a not-yet-uploaded product."""

    def __init__(
        self,
        *,
        image_processing_service: ImageProcessingService | None = None,
        catalog_intelligence_service: CatalogIntelligenceService | None = None,
        duplicate_detection_service: DuplicateDetectionService | None = None,
        duplicate_verification_service: DuplicateVerificationService | None = None,
        verification_enabled: bool | None = None,
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
        self._duplicate_verification_service = (
            duplicate_verification_service
            if duplicate_verification_service is not None
            else DuplicateVerificationService()
        )
        self._verification_enabled = (
            verification_enabled
            if verification_enabled is not None
            else settings.duplicate_verification.enabled
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
        price: float | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> DuplicateVerification:
        """Check whether a product described by `image`/metadata looks like a duplicate.

        `image` must describe a file `UploadService` has already written
        under this service's `upload_dir` — the same contract
        `ProductService.process_upload` has. When cross-encoder
        verification is enabled, `price` feeds the business-rule
        validation and `top_k`/`threshold` (the weighted-path per-request
        overrides) don't apply — the verification path uses its own
        configured cross-encoder threshold. Raises whatever
        `ImageProcessingService`/`CatalogIntelligenceService`/
        `DuplicateDetectionService`/`DuplicateVerificationService` raise
        for their own failure modes.
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

        if self._verification_enabled:
            return await self._duplicate_verification_service.verify(
                name=name,
                brand=brand,
                category=category,
                description=description,
                image=image,
                price=price,
                attributes=catalog_result.attributes,
                top_k=top_k,
            )

        decision = await self._duplicate_detection_service.detect(
            name=name,
            brand=brand,
            category=category,
            description=description,
            attributes=catalog_result.attributes,
            image=image,
            top_k=top_k,
            threshold=threshold,
        )
        return decision_to_verification(decision)


def decision_to_verification(decision: DuplicateDecision) -> DuplicateVerification:
    """Adapt a weighted-similarity `DuplicateDecision` into the unified `DuplicateVerification` shape.

    `cross_encoder_score`/`retrieval_similarity` are `None` — the weighted
    path computed neither — so a caller can tell "verification wasn't run"
    apart from "the cross-encoder scored it 0.0". The decision's single
    `reason` string becomes one `VerificationReason` (omitted entirely
    when it's empty, since a `VerificationReason` requires a non-blank
    message).
    """
    reasons = (
        [VerificationReason(code="weighted_similarity", message=decision.reason)]
        if decision.reason
        else []
    )
    return DuplicateVerification(
        is_duplicate=decision.is_duplicate,
        confidence=decision.confidence,
        cross_encoder_score=None,
        retrieval_similarity=None,
        matched_product=decision.matched_product,
        reasons=reasons,
        top_candidates=decision.top_candidates,
    )
