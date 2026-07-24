"""Product processing service: the pipeline stage between "a file is
saved" (Phase 2A's `UploadService`) and "here is a normalized, identified,
internally-consistent `Product` domain object" (this phase).

`ProductService.process_upload` orchestrates, in order: locate the
already-stored file and compute its checksum (`ChecksumService`),
standardize the image itself — orientation, color mode, size —
(`ImageProcessingService`, Phase 3), generate a semantic embedding from
the standardized image (`CLIPEmbeddingService`, Phase 4), parse internal
file metadata (`app.utils.metadata.parse_file_metadata`), normalize the
submitted product fields (the module-level `_normalize_*` functions
below), re-validate the normalized result
(`app.validators.product_validator`), generate a UUID4 identifier, and
build the `Product` domain model. No database write, no vector search,
no duplicate detection — see `backend/README.md`.

Kept as an orchestrator, not a place where new validation/normalization
*rules* get invented inline: normalization is small pure functions here
(easy to unit test directly), validation delegates entirely to
`app.validators.*`, image processing delegates entirely to
`ImageProcessingService`, and embedding generation delegates entirely to
`CLIPEmbeddingService`. `app/api/products.py` calls this service and
`UploadService` and nothing else — the router itself has no business logic.
"""

import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.models.embedding import ImageEmbedding
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductImage
from app.services.checksum_service import ChecksumService
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.utils.metadata import parse_file_metadata
from app.validators.product_validator import validate_normalized_name, validate_price

logger = get_logger(__name__)


class ProductService:
    """Orchestrates turning an uploaded file + submitted metadata into a `Product`."""

    def __init__(
        self,
        *,
        checksum_service: ChecksumService | None = None,
        image_processing_service: ImageProcessingService | None = None,
        embedding_service: BaseEmbeddingService | None = None,
        upload_dir: Path | None = None,
    ) -> None:
        self._checksum_service = (
            checksum_service if checksum_service is not None else ChecksumService()
        )
        self._image_processing_service = (
            image_processing_service
            if image_processing_service is not None
            else ImageProcessingService()
        )
        self._embedding_service = (
            embedding_service if embedding_service is not None else CLIPEmbeddingService()
        )
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir

    async def process_upload(self, product: ProductCreate, image: ProductImage) -> Product:
        """Process one uploaded product image into a `Product` domain object.

        `image` must describe a file `UploadService` has already written
        under this service's `upload_dir`. Raises `ChecksumException` if
        that file can't be read; `InvalidImageException`,
        `UnsupportedMediaTypeException`, or `ImageTooLargeException` if it
        fails image validation/processing (see `ImageProcessingService`);
        or `ValidationException` if the normalized product fields fail a
        domain invariant.
        """
        logger.info(
            "Upload processing started: product_name=%s, filename=%s",
            product.name,
            image.original_filename,
        )

        stored_path = self._upload_dir / image.stored_filename
        checksum = await self._checksum_service.compute_sha256(stored_path)
        logger.info(
            "Checksum generated: filename=%s, checksum=%s",
            image.stored_filename,
            checksum,
        )

        image_metadata = await self._image_processing_service.process_image(
            stored_path, image.stored_filename
        )

        vector = await self._embedding_service.generate_embedding(image_metadata.processed_path)
        logger.info(
            "Embedding generated: filename=%s, dimension=%d",
            image.stored_filename,
            len(vector),
        )

        file_metadata = parse_file_metadata(image, checksum_sha256=checksum)

        normalized_name = _normalize_name(product.name)
        normalized_description = _normalize_description(product.description)
        normalized_category = _normalize_category(product.category)
        normalized_price = _normalize_price(product.price)

        validate_normalized_name(normalized_name)
        validate_price(normalized_price)
        logger.info("Normalization complete: product_name=%s", normalized_name)

        product_id = uuid.uuid4()
        embedding = ImageEmbedding(
            product_id=product_id,
            model_name=self._embedding_service.model_name,
            embedding_dimension=len(vector),
            vector=vector,
        )
        domain_product = Product(
            id=product_id,
            name=normalized_name,
            description=normalized_description,
            category=normalized_category,
            price=normalized_price,
            file_metadata=file_metadata,
            image_metadata=image_metadata,
            embedding=embedding,
        )

        logger.info("Product processed: id=%s, name=%s", product_id, normalized_name)
        return domain_product


def _normalize_name(name: str) -> str:
    """Trim surrounding whitespace only — names may be brand names/proper nouns, so case is preserved."""
    return name.strip()


def _normalize_description(description: str | None) -> str | None:
    """Trim surrounding whitespace; an all-whitespace description normalizes to `None`."""
    if description is None:
        return None
    trimmed = description.strip()
    return trimmed or None


def _normalize_category(category: str | None) -> str | None:
    """Lowercase and slugify: `"Men Tshirts"` -> `"men-tshirts"`.

    Runs of non-alphanumeric characters (spaces, underscores, punctuation)
    become a single hyphen, and leading/trailing hyphens are stripped — a
    category that's blank after normalizing becomes `None`.
    """
    if category is None:
        return None
    lowered = category.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or None


def _normalize_price(price: float | None) -> float | None:
    """Round to 2 decimal places (currency precision): `1999` -> `1999.0` (displayed as `1999.00`)."""
    if price is None:
        return None
    return round(price, 2)
