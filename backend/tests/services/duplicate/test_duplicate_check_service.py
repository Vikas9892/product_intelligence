"""Unit tests for `DuplicateCheckService`.

Composes fake `ImageProcessingService`/`CatalogIntelligenceService`/
`DuplicateDetectionService` doubles (each already covered by their own
test modules) so this orchestrator's own sequencing/wiring can be tested
in isolation.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_verification import DuplicateVerification
from app.models.image_metadata import ImageMetadata
from app.models.product_attributes import ProductAttributes
from app.models.verification_reason import VerificationReason
from app.schemas.product import ProductImage
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.duplicate.duplicate_check_service import DuplicateCheckService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.duplicate.duplicate_verification_service import DuplicateVerificationService
from app.services.image_processing_service import ImageProcessingService


class _FakeImageProcessingService(ImageProcessingService):
    def __init__(self) -> None:
        self.calls: list[Path] = []

    async def process_image(self, stored_path: Path, stored_filename: str) -> ImageMetadata:
        self.calls.append(stored_path)
        return ImageMetadata(
            width=100,
            height=100,
            format="JPEG",
            color_mode="RGB",
            original_path=stored_path,
            processed_path=stored_path.parent / "processed" / stored_filename,
        )


class _FakeCatalogIntelligenceService(CatalogIntelligenceService):
    def __init__(self, *, attributes: ProductAttributes | None = None) -> None:
        self._attributes = attributes if attributes is not None else ProductAttributes()
        self.image_paths: list[Path] = []

    async def enrich(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image_path: Path,
    ) -> CatalogIntelligenceResult:
        self.image_paths.append(image_path)
        return CatalogIntelligenceResult(
            attributes=self._attributes, tags=[], quality_score=0.0, processing_time=0.0
        )


class _FakeDuplicateDetectionService(DuplicateDetectionService):
    def __init__(self, *, decision: DuplicateDecision) -> None:
        self._decision = decision
        self.received_attributes: ProductAttributes | None = None
        self.received_top_k: int | None = None
        self.received_threshold: float | None = None

    async def detect(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        attributes: ProductAttributes,
        image: ProductImage,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        self.received_attributes = attributes
        self.received_top_k = top_k
        self.received_threshold = threshold
        return self._decision


class _FakeDuplicateVerificationService(DuplicateVerificationService):
    def __init__(self, *, verification: DuplicateVerification) -> None:
        self._verification = verification
        self.received_price: float | None = None
        self.received_attributes: ProductAttributes | None = None

    async def verify(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image: ProductImage,
        price: float | None = None,
        attributes: ProductAttributes | None = None,
        top_k: int | None = None,
    ) -> DuplicateVerification:
        self.received_price = price
        self.received_attributes = attributes
        return self._verification


def _image() -> ProductImage:
    return ProductImage(
        original_filename="photo.jpg",
        stored_filename="stored.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        uploaded_at=datetime.now(UTC),
    )


class TestDuplicateCheckService:
    async def test_wires_catalog_intelligence_attributes_into_duplicate_detection(
        self, tmp_path: Path
    ) -> None:
        attributes = ProductAttributes(color="Red")
        catalog_intelligence_service = _FakeCatalogIntelligenceService(attributes=attributes)
        duplicate_detection_service = _FakeDuplicateDetectionService(
            decision=DuplicateDecision(is_duplicate=False, confidence=0.1, reason="no match")
        )
        service = DuplicateCheckService(
            image_processing_service=_FakeImageProcessingService(),
            catalog_intelligence_service=catalog_intelligence_service,
            duplicate_detection_service=duplicate_detection_service,
            upload_dir=tmp_path,
        )

        await service.check(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert duplicate_detection_service.received_attributes == attributes

    async def test_passes_top_k_and_threshold_overrides_through(self, tmp_path: Path) -> None:
        duplicate_detection_service = _FakeDuplicateDetectionService(
            decision=DuplicateDecision(is_duplicate=False, confidence=0.1, reason="no match")
        )
        service = DuplicateCheckService(
            image_processing_service=_FakeImageProcessingService(),
            catalog_intelligence_service=_FakeCatalogIntelligenceService(),
            duplicate_detection_service=duplicate_detection_service,
            upload_dir=tmp_path,
        )

        await service.check(
            name="Widget",
            brand=None,
            category=None,
            description=None,
            image=_image(),
            top_k=3,
            threshold=0.5,
        )

        assert duplicate_detection_service.received_top_k == 3
        assert duplicate_detection_service.received_threshold == 0.5

    async def test_adapts_the_detection_decision_into_a_verification(self, tmp_path: Path) -> None:
        decision = DuplicateDecision(is_duplicate=True, confidence=0.97, reason="matched")
        service = DuplicateCheckService(
            image_processing_service=_FakeImageProcessingService(),
            catalog_intelligence_service=_FakeCatalogIntelligenceService(),
            duplicate_detection_service=_FakeDuplicateDetectionService(decision=decision),
            verification_enabled=False,
            upload_dir=tmp_path,
        )

        result = await service.check(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        # Weighted path: the decision is adapted into DuplicateVerification
        # with the cross-encoder/retrieval fields left None.
        assert result.is_duplicate is True
        assert result.confidence == 0.97
        assert result.cross_encoder_score is None
        assert result.retrieval_similarity is None
        assert [r.message for r in result.reasons] == ["matched"]

    async def test_processes_the_stored_file_under_the_configured_upload_dir(
        self, tmp_path: Path
    ) -> None:
        image_processing_service = _FakeImageProcessingService()
        service = DuplicateCheckService(
            image_processing_service=image_processing_service,
            catalog_intelligence_service=_FakeCatalogIntelligenceService(),
            duplicate_detection_service=_FakeDuplicateDetectionService(
                decision=DuplicateDecision(is_duplicate=False, confidence=0.0, reason="")
            ),
            upload_dir=tmp_path,
        )

        await service.check(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert image_processing_service.calls == [tmp_path / "stored.jpg"]


class TestDuplicateCheckServiceVerificationPath:
    async def test_delegates_to_verification_when_enabled(self, tmp_path: Path) -> None:
        verification = DuplicateVerification(
            is_duplicate=True,
            confidence=0.97,
            cross_encoder_score=0.98,
            retrieval_similarity=0.94,
            reasons=[VerificationReason(code="same_brand", message="Same brand (Nike)")],
        )
        verification_service = _FakeDuplicateVerificationService(verification=verification)
        service = DuplicateCheckService(
            image_processing_service=_FakeImageProcessingService(),
            catalog_intelligence_service=_FakeCatalogIntelligenceService(),
            duplicate_verification_service=verification_service,
            verification_enabled=True,
            upload_dir=tmp_path,
        )

        result = await service.check(
            name="Widget", brand="Nike", category=None, description=None, image=_image()
        )

        assert result == verification
        assert result.cross_encoder_score == 0.98

    async def test_forwards_price_and_catalog_attributes_to_verification(
        self, tmp_path: Path
    ) -> None:
        attributes = ProductAttributes(color="Red")
        verification_service = _FakeDuplicateVerificationService(
            verification=DuplicateVerification(is_duplicate=False, confidence=0.1)
        )
        service = DuplicateCheckService(
            image_processing_service=_FakeImageProcessingService(),
            catalog_intelligence_service=_FakeCatalogIntelligenceService(attributes=attributes),
            duplicate_verification_service=verification_service,
            verification_enabled=True,
            upload_dir=tmp_path,
        )

        await service.check(
            name="Widget",
            brand="Nike",
            category=None,
            description=None,
            image=_image(),
            price=99.0,
        )

        assert verification_service.received_price == 99.0
        assert verification_service.received_attributes == attributes
