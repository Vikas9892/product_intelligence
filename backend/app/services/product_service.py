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
after the image embedding), parse internal file metadata
(`app.utils.metadata.parse_file_metadata`), normalize the submitted
product fields (the module-level `_normalize_*` functions below),
re-validate the normalized result (`app.validators.product_validator`),
generate a UUID4 identifier, build the `Product` domain model, and upsert
both embeddings into their respective vector store collections
(`BaseVectorStore`, Phases 5-6) so the product is immediately searchable
by image or by text. No database write, no duplicate detection — see
`backend/README.md`.

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

**Why does the text representation use the raw submitted
brand/category — not `_normalize_category`'s slugified result
(`"men-tshirts"`)?** Slugifying exists so category is a stable,
exact-match filter value; it's actively a worse input for a *semantic*
text embedding model, which should see natural language ("Men Tshirts"),
not a URL-safe slug. The two normalizations serve different purposes
(filtering vs. meaning) and are kept independent — see
`_build_text_representation`'s own docstring.

Kept as an orchestrator, not a place where new validation/normalization
*rules* get invented inline: normalization is small pure functions here
(easy to unit test directly), validation delegates entirely to
`app.validators.*`, image processing delegates entirely to
`ImageProcessingService`, embedding generation delegates entirely to
`CLIPEmbeddingService`/`BaseTextEmbeddingService`, and vector storage
delegates entirely to `BaseVectorStore`. `app/api/products.py` calls this
service and `UploadService` and nothing else — the router itself has no
business logic.
"""

import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.models.embedding import ImageEmbedding
from app.models.product import Product
from app.models.text_embedding import TextEmbedding
from app.schemas.product import ProductCreate, ProductImage
from app.services.checksum_service import ChecksumService
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
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
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

        text_representation = _build_text_representation(
            product.name, product.brand, product.category, product.description
        )
        text_vector = await self._text_embedding_service.embed_text(text_representation)
        logger.info(
            "Text embedding generated: filename=%s, dimension=%d",
            image.stored_filename,
            len(text_vector),
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

        product_id = uuid.uuid4()
        embedding = ImageEmbedding(
            product_id=product_id,
            model_name=self._embedding_service.model_name,
            embedding_dimension=len(vector),
            vector=vector,
        )
        text_embedding = TextEmbedding(
            product_id=product_id,
            model_name=self._text_embedding_service.model_name,
            embedding_dimension=len(text_vector),
            vector=text_vector,
        )
        domain_product = Product(
            id=product_id,
            name=normalized_name,
            brand=normalized_brand,
            description=normalized_description,
            category=normalized_category,
            price=normalized_price,
            file_metadata=file_metadata,
            image_metadata=image_metadata,
            embedding=embedding,
            text_embedding=text_embedding,
        )

        vector_metadata = {
            "name": normalized_name,
            "brand": normalized_brand,
            "category": normalized_category,
            "price": normalized_price,
            "description": normalized_description,
        }
        await self._vector_store.upsert_image(
            [VectorRecord(product_id=product_id, vector=embedding.vector, metadata=vector_metadata)]
        )
        await self._vector_store.upsert_text(
            [
                VectorRecord(
                    product_id=product_id, vector=text_embedding.vector, metadata=vector_metadata
                )
            ]
        )
        logger.info("Product embeddings upserted into vector store: id=%s", product_id)

        logger.info("Product processed: id=%s, name=%s", product_id, normalized_name)
        return domain_product


def _build_text_representation(
    name: str, brand: str | None, category: str | None, description: str | None
) -> str:
    """Join the product's name/brand/category/description into one natural-language string.

    Deliberately uses the *raw* submitted values (only stripped of
    surrounding whitespace), not `_normalize_category`'s slugified result
    (`"men-tshirts"`) — a sentence embedding model should see "Men
    Tshirts", not a URL-safe slug. Slugifying exists purely so category
    is a stable, exact-match filter value for the vector store; it's a
    storage/filtering concern, not a semantic-meaning one, so this
    function intentionally doesn't call `_normalize_category`.
    """
    parts = [name.strip()]
    for part in (brand, category, description):
        if part and part.strip():
            parts.append(part.strip())
    return ". ".join(parts)


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
