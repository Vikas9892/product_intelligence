"""`ProductImageService`: reads a product's stored image back off disk.

The system indexes images, prices from image similarity and detects duplicates
partly on visual signal -- and until now could not show the user the image it
reasoned about. Uploads were stored and processed, but no route read them back,
so the UI apologised for a capability that had simply never been built.

Two things make that fixable rather than a redesign:

* Both variants are retained. `UploadService` writes the original under
  `storage/uploads/`, `ImageProcessingService` writes a standardized JPEG under
  `storage/processed/`, and neither is deleted afterwards.
* The processed filename is *derivable* from the stored one
  (`generate_processed_filename`), so one recorded name locates both.

Security
--------

This is the one route in the API that turns an identifier into a filesystem
read, so it is the one place a path-traversal bug would matter.

Nothing user-supplied reaches the filesystem. The client supplies a UUID; the
filename is read from the product's own stored payload, and it was generated
by `UploadService` (never the client's filename -- that module documents the
traversal/collision reasoning). As defence in depth, every resolved path is
then checked to be inside the configured storage root before it is opened, so
even a corrupted payload cannot escape it.
"""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from PIL import Image

from app.core import constants
from app.core.config import settings
from app.core.logging import get_logger
from app.services.product_lookup_service import ProductLookupService
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.utils.image import generate_processed_filename

logger = get_logger(__name__)

#: Longest edge of the thumbnail variant, in pixels.
#:
#: Recommendation cards and search results render many images at small sizes;
#: serving the full standardized image (1024px) for a card displayed at ~200px
#: wastes bandwidth on every one. 320 covers a 2x retina card without being a
#: second full-size asset.
THUMBNAIL_SIZE_PX = 320

#: Cache lifetime for a served image.
#:
#: Long, because these are immutable: a stored image is written once during
#: ingestion and never modified, and re-uploading produces a new product with a
#: new filename. `immutable` tells a browser not to revalidate at all.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


@dataclass(frozen=True)
class ResolvedImage:
    """A product image located on disk and ready to serve."""

    path: Path
    media_type: str
    cache_control: str = _CACHE_CONTROL


class ProductImageNotFoundError(Exception):
    """No image is stored for this product.

    Distinct from "the product does not exist" and from "the API cannot serve
    images" -- three states that looked identical to a user before this route
    existed, and which the caller renders differently.
    """


class ProductImageService:
    """Resolves a product id to its stored image file."""

    def __init__(
        self,
        *,
        vector_store: BaseVectorStore | None = None,
        lookup_service: ProductLookupService | None = None,
        upload_dir: Path | None = None,
        processed_dir: Path | None = None,
        thumbnail_dir: Path | None = None,
    ) -> None:
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._lookup_service = (
            lookup_service
            if lookup_service is not None
            else ProductLookupService(vector_store=self._vector_store)
        )
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir
        self._processed_dir = (
            processed_dir if processed_dir is not None else settings.storage.processed_dir
        )
        self._thumbnail_dir = (
            thumbnail_dir if thumbnail_dir is not None else self._processed_dir / "thumbnails"
        )

    async def resolve(self, product_id: UUID, *, thumbnail: bool = False) -> ResolvedImage:
        """Locate `product_id`'s image.

        Serves the *processed* variant rather than the original upload: it is
        already normalized, re-encoded to one format and bounded in size, so it
        is both smaller and predictable to a client. The original stays on disk
        as the archival copy.

        Raises `ProductImageNotFoundError` when the product carries no image
        reference, or the referenced file is gone.
        """
        filename = await self._image_filename(product_id)
        if filename is None:
            raise ProductImageNotFoundError(
                f"Product '{product_id}' has no stored image. Products indexed "
                f"before image serving existed do not carry an image reference."
            )

        processed = self._safe_path(self._processed_dir, generate_processed_filename(filename))
        if processed is None or not processed.is_file():
            # Fall back to the original: an upload whose processing failed
            # still has its source file, and showing it beats showing nothing.
            original = self._safe_path(self._upload_dir, filename)
            if original is None or not original.is_file():
                raise ProductImageNotFoundError(
                    f"Product '{product_id}' references image '{filename}', but no file "
                    f"for it exists in storage."
                )
            return ResolvedImage(path=original, media_type=_media_type_for(original))

        if thumbnail:
            return ResolvedImage(
                path=self._thumbnail(processed), media_type=constants.PROCESSED_IMAGE_MEDIA_TYPE
            )
        return ResolvedImage(path=processed, media_type=constants.PROCESSED_IMAGE_MEDIA_TYPE)

    async def _image_filename(self, product_id: UUID) -> str | None:
        """Read the stored image filename from the product's own payload."""
        point = await self._vector_store.retrieve_image(product_id)
        if point is None:
            point = await self._vector_store.retrieve_text(product_id)
        if point is None:
            return None
        filename = point.metadata.get("image_filename")
        return filename if isinstance(filename, str) and filename.strip() else None

    def _safe_path(self, root: Path, filename: str) -> Path | None:
        """Join `filename` under `root`, or `None` if the result escapes it.

        Defence in depth. `filename` comes from the product's stored payload
        and was generated server-side, so it should never contain a separator
        or `..` -- but a route that reads the filesystem should not rely on
        "should never".
        """
        candidate = (root / filename).resolve()
        resolved_root = root.resolve()
        if not candidate.is_relative_to(resolved_root):
            logger.warning("Rejected an image path outside the storage root: filename=%r", filename)
            return None
        return candidate

    def _thumbnail(self, processed: Path) -> Path:
        """Return a small variant of `processed`, generating it once on demand.

        Written next to the processed images rather than produced per request:
        a recommendation list re-renders often, and re-encoding the same JPEG
        each time is pure waste. The cached file is derived from an immutable
        source, so it never needs invalidating.
        """
        self._thumbnail_dir.mkdir(parents=True, exist_ok=True)
        cached = self._thumbnail_dir / processed.name
        if cached.is_file():
            return cached

        with Image.open(processed) as opened:
            # Rebound rather than reassigned: `convert` returns a new image, and
            # Pillow's stub types the `with` target more narrowly than the result.
            thumbnail_image = opened.convert("RGB")
            thumbnail_image.thumbnail(
                (THUMBNAIL_SIZE_PX, THUMBNAIL_SIZE_PX), Image.Resampling.LANCZOS
            )
            thumbnail_image.save(cached, format=constants.PROCESSED_IMAGE_FORMAT, quality=80)
        logger.info("Thumbnail generated: %s", cached.name)
        return cached


def _media_type_for(path: Path) -> str:
    """Media type for an original upload, from its extension."""
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
