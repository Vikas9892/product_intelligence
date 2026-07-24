"""Internal file metadata: the "Parse Metadata" pipeline stage.

`FileMetadata` is a transport-agnostic description of one stored file —
distinct from `app.schemas.product.ProductImage` (Phase 2A's API-facing
model returned in HTTP responses). `parse_file_metadata` is the adapter
between the two: it takes what `UploadService` already knows about a
stored file (`ProductImage`) plus a separately-computed checksum
(`ChecksumService`), and produces the richer internal object
`app.services.product_service.ProductService` builds a `Product` domain
model from.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.schemas.product import ProductImage

# A SHA-256 digest is always 64 lowercase hex characters — `hexdigest()`
# guarantees this, so validating the shape here catches a caller passing
# something else (a truncated string, a differently-encoded hash) early.
_SHA256_HEX_PATTERN = r"^[0-9a-f]{64}$"


class FileMetadata(BaseModel):
    """Internal, transport-agnostic metadata describing one uploaded file."""

    original_filename: str
    extension: str
    content_type: str
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=_SHA256_HEX_PATTERN)
    uploaded_at: datetime


def parse_file_metadata(image: ProductImage, *, checksum_sha256: str) -> FileMetadata:
    """Build `FileMetadata` from an already-stored file's `ProductImage` and checksum.

    The extension is re-derived from `original_filename` rather than
    reused from wherever `UploadService` already computed one, so this
    function has a single source of truth for "what is this file's
    extension" independent of the caller's internals.
    """
    extension = Path(image.original_filename).suffix.lower()
    return FileMetadata(
        original_filename=image.original_filename,
        extension=extension,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        checksum_sha256=checksum_sha256,
        uploaded_at=image.uploaded_at,
    )
