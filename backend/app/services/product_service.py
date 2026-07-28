"""Product processing service: the pipeline stage between "a file is
saved" (Phase 2A's `UploadService`) and "here is a normalized, identified,
internally-consistent `Product` domain object" (this phase).

`ProductService.process_upload` orchestrates, in order: locate the
already-stored file and compute its checksum (`ChecksumService`),
standardize the image itself — orientation, color mode, size —
(`ImageProcessingService`, Phase 3), generate a semantic embedding from
the standardized image (`CLIPEmbeddingService`, Phase 4), build a text
representation from the product's name/brand/category/description and
embed it too (`BaseTextEmbeddingService`, Phase 6 — generated immediately
after the image embedding), run catalog intelligence enrichment
(`CatalogIntelligenceService`, Phase 7 — extracted attributes, generated
tags, a quality score), evaluate the product for duplicates
(`DuplicateDetectionService`, Phase 8 — hybrid search for similar
existing products, scored, thresholded into a `DuplicateDecision`; a
`BLOCK`-mode duplicate raises `ConflictException` here, before anything
below runs), parse internal file metadata
(`app.utils.metadata.parse_file_metadata`), normalize the submitted
product fields (the module-level `_normalize_*` functions below),
re-validate the normalized result (`app.validators.product_validator`),
resolve a UUID4 identifier (generated here, or passed in by the caller —
Phase 12's `ProductWorker` pre-assigns one so a retried job keeps the
same ID across attempts), build the `Product` domain model, and upsert
both embeddings — now carrying the enriched attributes/tags as
additional metadata — into their respective vector store collections
(`BaseVectorStore`, Phases 5-6) so the product is immediately searchable
by image or by text. No database write — see `backend/README.md`.

**Why does duplicate detection run *before* normalization/validation and
the vector store upsert, not after?** `BLOCK` mode must reject a likely
duplicate "before persistence" (the phase's own framing) — indexing it
first and then deciding to reject would briefly make a rejected upload
searchable, and would need a compensating delete on rejection. Running it
early means a blocked upload never reaches the vector store at all, no
cleanup required.

**Why does `ProductService` — not a later, separate step — upsert into
the vector store?** `SearchService`/`TextSearchService`/`HybridSearchService`
can only ever find products that already have an entry in the vector
store; without this, every search would return empty results forever,
regardless of how correct the search pipeline itself is. Upserting
immediately after building the `Product`, in the same request, keeps "a
product is uploaded" and "a product is searchable" a single
atomic-feeling step for a caller, the same way embedding generation
itself was folded in here in Phase 4 rather than left as a separate,
easy-to-forget follow-up call.

**Why does the text representation (and catalog intelligence enrichment)
use the raw submitted brand/category — not `_normalize_category`'s
slugified result (`"men-tshirts"`)?** Slugifying exists so category is a
stable, exact-match filter value; it's actively a worse input for a
*semantic* text embedding model or a text attribute extractor, both of
which should see natural language ("Men Tshirts"), not a URL-safe slug.
The two normalizations serve different purposes (filtering vs. meaning)
and are kept independent — see `app.utils.text.build_text_representation`'s own
docstring.

**Why does `brand`/`category` in the vector store's metadata stay the
already-established normalized/slugified values, while `color`/
`material`/`gender`/`season`/`style`/`tags`/`quality_score` come straight
from `CatalogIntelligenceResult`?** Changing what `brand`/`category` mean
in already-indexed metadata would silently break `ProductFilters`
equality matching (Phase 6) for anything indexed before this phase; the
newer fields have no prior meaning to preserve, so they're populated
directly from whatever catalog intelligence resolved (which may be
`None`, same as any other optional attribute). `quality_score` (Phase 9)
is what `RecommendationScorer` reads back out of a candidate's metadata
for its own "Catalog Quality" signal — it's the only place a candidate's
quality score is available once retrieval happens via `HybridSearchService`
rather than a fresh `CatalogIntelligenceResult`.

**How do the three `DuplicateDetectionMode`s (`OFF`/`WARN`/`BLOCK`)
change this pipeline?** `OFF` skips `DuplicateDetectionService` entirely
— `Product.duplicate_decision` is still always populated (mirroring
`catalog_intelligence`'s "always present" convention), just with a
neutral "detection is disabled" decision rather than `None`, so callers
never have to branch on whether the field itself exists. `WARN` runs
detection and stores the product regardless of the outcome — the
decision is simply attached to `UploadResponse` for the caller's own
judgment. `BLOCK` runs the exact same detection but raises
`ConflictException` (409) instead of proceeding when `is_duplicate` is
`True` — the upload is rejected outright, never reaching normalization,
`Product` construction, or the vector store.

Kept as an orchestrator, not a place where new validation/normalization
*rules* get invented inline: normalization is small pure functions here
(easy to unit test directly), validation delegates entirely to
`app.validators.*`, image processing delegates entirely to
`ImageProcessingService`, embedding generation delegates entirely to
`CLIPEmbeddingService`/`BaseTextEmbeddingService`, catalog enrichment
delegates entirely to `CatalogIntelligenceService`, duplicate detection
delegates entirely to `DuplicateDetectionService`, and vector storage
delegates entirely to `BaseVectorStore`. `app/api/products.py` calls this
service and `UploadService` and nothing else — the router itself has no
business logic.
"""

import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.constants import DuplicateDetectionMode
from app.core.logging import get_logger
from app.exceptions.errors import ConflictException
from app.models.catalog_intelligence_result import CatalogIntelligenceResult
from app.models.duplicate_decision import DuplicateDecision
from app.models.embedding import ImageEmbedding
from app.models.product import Product
from app.models.product_attributes import ProductAttributes
from app.models.text_embedding import TextEmbedding
from app.schemas.product import ProductCreate, ProductImage
from app.services.catalog.catalog_intelligence_service import CatalogIntelligenceService
from app.services.checksum_service import ChecksumService
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.sentence_transformer_service import (
    SentenceTransformerEmbeddingService,
)
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.image_processing_service import ImageProcessingService
from app.services.vectorstore.base import BaseVectorStore, VectorRecord
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.utils.metadata import parse_file_metadata
from app.utils.text import build_text_representation
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
        text_embedding_service: BaseTextEmbeddingService | None = None,
        catalog_intelligence_service: CatalogIntelligenceService | None = None,
        catalog_intelligence_enabled: bool | None = None,
        duplicate_detection_service: DuplicateDetectionService | None = None,
        duplicate_detection_mode: DuplicateDetectionMode | None = None,
        vector_store: BaseVectorStore | None = None,
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
        self._text_embedding_service = (
            text_embedding_service
            if text_embedding_service is not None
            else SentenceTransformerEmbeddingService()
        )
        self._catalog_intelligence_service = (
            catalog_intelligence_service
            if catalog_intelligence_service is not None
            else CatalogIntelligenceService()
        )
        self._catalog_intelligence_enabled = (
            catalog_intelligence_enabled
            if catalog_intelligence_enabled is not None
            else settings.catalog_intelligence.enabled
        )
        self._duplicate_detection_service = (
            duplicate_detection_service
            if duplicate_detection_service is not None
            else DuplicateDetectionService()
        )
        self._duplicate_detection_mode = (
            duplicate_detection_mode
            if duplicate_detection_mode is not None
            else settings.duplicate_detection.mode
        )
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir

    async def process_upload(
        self, product: ProductCreate, image: ProductImage, *, product_id: uuid.UUID | None = None
    ) -> Product:
        """Process one uploaded product image into a `Product` domain object.

        `image` must describe a file `UploadService` has already written
        under this service's `upload_dir`. `product_id` lets a caller
        pre-assign the identifier instead of one being generated here
        (Phase 12's `ProductWorker` passes the same `product_id` its job
        was created with, so a retried job re-processes under the exact
        same ID — Qdrant's upsert then makes the whole pipeline naturally
        idempotent under retries, rather than creating a second indexed
        point per attempt); omitted, a new UUID4 is generated exactly as
        before. Raises `ChecksumException` if that file can't be read;
        `InvalidImageException`, `UnsupportedMediaTypeException`, or
        `ImageTooLargeException` if it fails image validation/processing
        (see `ImageProcessingService`); `ValidationException` if the
        normalized product fields fail a domain invariant; or
        `ConflictException` (409) if `DuplicateDetectionMode.BLOCK` is
        configured and the product is flagged as a likely duplicate.
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

        text_representation = build_text_representation(
            product.name, product.brand, product.category, product.description
        )
        text_vector = await self._text_embedding_service.embed_text(text_representation)
        logger.info(
            "Text embedding generated: filename=%s, dimension=%d",
            image.stored_filename,
            len(text_vector),
        )

        if self._catalog_intelligence_enabled:
            catalog_result = await self._catalog_intelligence_service.enrich(
                name=product.name,
                brand=product.brand,
                category=product.category,
                description=product.description,
                image_path=image_metadata.processed_path,
            )
        else:
            catalog_result = CatalogIntelligenceResult(
                attributes=ProductAttributes(), tags=[], quality_score=0.0, processing_time=0.0
            )
        logger.info(
            "Catalog intelligence enrichment applied: filename=%s, tags=%d, quality_score=%.2f",
            image.stored_filename,
            len(catalog_result.tags),
            catalog_result.quality_score,
        )

        if self._duplicate_detection_mode is DuplicateDetectionMode.OFF:
            duplicate_decision = DuplicateDecision(
                is_duplicate=False, confidence=0.0, reason="Duplicate detection is disabled."
            )
        else:
            duplicate_decision = await self._duplicate_detection_service.detect(
                name=product.name,
                brand=product.brand,
                category=product.category,
                description=product.description,
                attributes=catalog_result.attributes,
                image=image,
            )
            logger.info(
                "Duplicate detection complete: filename=%s, is_duplicate=%s, confidence=%.2f",
                image.stored_filename,
                duplicate_decision.is_duplicate,
                duplicate_decision.confidence,
            )
            is_blocking = self._duplicate_detection_mode is DuplicateDetectionMode.BLOCK
            if duplicate_decision.is_duplicate and is_blocking:
                logger.warning(
                    "Upload rejected as a likely duplicate: filename=%s, "
                    "matched_product=%s, confidence=%.2f",
                    image.stored_filename,
                    duplicate_decision.matched_product,
                    duplicate_decision.confidence,
                )
                raise ConflictException(
                    f"This product appears to be a duplicate of an existing product "
                    f"(confidence={duplicate_decision.confidence:.2f}).",
                    details={
                        "matched_product": str(duplicate_decision.matched_product),
                        "confidence": duplicate_decision.confidence,
                    },
                )

        file_metadata = parse_file_metadata(image, checksum_sha256=checksum)

        normalized_name = _normalize_name(product.name)
        normalized_brand = _normalize_brand(product.brand)
        normalized_description = _normalize_description(product.description)
        normalized_category = _normalize_category(product.category)
        normalized_price = _normalize_price(product.price)

        validate_normalized_name(normalized_name)
        validate_price(normalized_price)
        logger.info("Normalization complete: product_name=%s", normalized_name)

        resolved_product_id = product_id if product_id is not None else uuid.uuid4()
        embedding = ImageEmbedding(
            product_id=resolved_product_id,
            model_name=self._embedding_service.model_name,
            embedding_dimension=len(vector),
            vector=vector,
        )
        text_embedding = TextEmbedding(
            product_id=resolved_product_id,
            model_name=self._text_embedding_service.model_name,
            embedding_dimension=len(text_vector),
            vector=text_vector,
        )
        domain_product = Product(
            id=resolved_product_id,
            name=normalized_name,
            brand=normalized_brand,
            description=normalized_description,
            category=normalized_category,
            price=normalized_price,
            file_metadata=file_metadata,
            image_metadata=image_metadata,
            embedding=embedding,
            text_embedding=text_embedding,
            catalog_intelligence=catalog_result,
            duplicate_decision=duplicate_decision,
        )

        vector_metadata = {
            "name": normalized_name,
            "brand": normalized_brand,
            "category": normalized_category,
            "price": normalized_price,
            "description": normalized_description,
            "color": catalog_result.attributes.color,
            "material": catalog_result.attributes.material,
            "gender": catalog_result.attributes.gender,
            "season": catalog_result.attributes.season,
            "style": catalog_result.attributes.style,
            "tags": [tag.tag for tag in catalog_result.tags],
            "quality_score": catalog_result.quality_score,
        }
        await self._vector_store.upsert_image(
            [
                VectorRecord(
                    product_id=resolved_product_id,
                    vector=embedding.vector,
                    metadata=vector_metadata,
                )
            ]
        )
        await self._vector_store.upsert_text(
            [
                VectorRecord(
                    product_id=resolved_product_id,
                    vector=text_embedding.vector,
                    metadata=vector_metadata,
                )
            ]
        )
        logger.info("Product embeddings upserted into vector store: id=%s", resolved_product_id)

        logger.info("Product processed: id=%s, name=%s", resolved_product_id, normalized_name)
        return domain_product


def _normalize_name(name: str) -> str:
    """Trim surrounding whitespace only — names may be brand names/proper nouns, so case is preserved."""
    return name.strip()


def _normalize_brand(brand: str | None) -> str | None:
    """Trim surrounding whitespace; an all-whitespace brand normalizes to `None` — same as `_normalize_description`."""
    if brand is None:
        return None
    trimmed = brand.strip()
    return trimmed or None


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
