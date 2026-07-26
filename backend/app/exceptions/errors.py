"""Concrete, domain-agnostic application exceptions.

Each subclass fixes one (`status_code`, `code`) pair for a category of
failure that recurs across any resource-oriented API. They're intentionally
generic ("a resource wasn't found", not "a product wasn't found") — a
later milestone's product/search code raises `ResourceNotFoundException`
the same way user/auth code eventually would, instead of every domain
reinventing its own not-found exception.
"""

from typing import Any

from app.exceptions.base import AppException


class ValidationException(AppException):
    """A request was semantically invalid in a way schema validation alone can't express.

    FastAPI already returns 422 for requests that fail Pydantic *schema*
    validation (missing/mistyped fields) — that path is handled separately
    in `handlers.py` via `RequestValidationError`. Raise this instead for
    validation that requires business logic to detect (e.g. "end_date must
    be after start_date"), which schema validation alone can't express.
    """

    status_code = 422
    code = "validation_error"
    message = "The request was invalid."


class ResourceNotFoundException(AppException):
    """The requested resource does not exist."""

    status_code = 404
    code = "resource_not_found"
    message = "The requested resource was not found."

    def __init__(self, message: str | None = None, *, resource: str | None = None) -> None:
        details: dict[str, Any] | None = {"resource": resource} if resource else None
        super().__init__(message, details=details)


class ConflictException(AppException):
    """The request conflicts with the current state of the resource.

    E.g. a uniqueness constraint violation, or a stale/optimistic-locking
    conflict on update.
    """

    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class UnsupportedMediaTypeException(AppException):
    """An uploaded file's extension or declared MIME type is not accepted.

    Distinct from `ValidationException` (422): this is specifically a
    415 "the payload itself is the wrong kind of thing", not "the request
    shape was wrong" — a client can tell the two apart by status code
    alone, without parsing `code`.
    """

    status_code = 415
    code = "unsupported_media_type"
    message = "The uploaded file's type is not supported."


class FileTooLargeException(AppException):
    """An uploaded file exceeds the configured maximum size."""

    status_code = 413
    code = "file_too_large"
    message = "The uploaded file exceeds the maximum allowed size."


class ChecksumException(AppException):
    """A stored file's checksum could not be computed.

    An infrastructure failure (the file vanished or became unreadable
    between being stored and being hashed), not a client input problem —
    hence a 500, unlike the 4xx upload-validation exceptions above.
    """

    status_code = 500
    code = "checksum_error"
    message = "Failed to compute the file's checksum."


class InvalidImageException(AppException):
    """An uploaded file claims to be an image but is corrupted or undecodable.

    Distinct from `UnsupportedMediaTypeException` (415): the file's
    extension/declared MIME type were already accepted by
    `file_validator` — this fires when Pillow can't actually make sense
    of the bytes (truncated data, a non-image file with a misleading
    extension, an unrecognized/unsupported decoded format). 422, not 415:
    the *kind* of upload was acceptable, its *content* wasn't.
    """

    status_code = 422
    code = "invalid_image"
    message = "The uploaded file is not a valid image."


class ImageTooLargeException(AppException):
    """An image's pixel dimensions exceed the configured maximum.

    Distinct from `FileTooLargeException` (byte size on disk): a small,
    heavily-compressed file can still decode to an enormous pixel grid
    (a classic decompression-bomb pattern) — this check is against actual
    decoded width/height, independent of the file's size in bytes.
    """

    status_code = 413
    code = "image_too_large"
    message = "The image's dimensions exceed the maximum allowed size."


class EmbeddingGenerationException(AppException):
    """An embedding could not be generated for an already-processed image.

    An infrastructure failure (the processed file vanished, the model
    failed to load, inference raised) rather than a client input
    problem — by the time this runs, `ImageProcessingService` has already
    confirmed the file is a valid, standardized image. Hence a 500, the
    same reasoning as `ChecksumException`.
    """

    status_code = 500
    code = "embedding_generation_error"
    message = "Failed to generate an embedding for the processed image."


class TextEmbeddingException(AppException):
    """A text embedding could not be generated for a product's text representation.

    An infrastructure failure (the model failed to load, inference
    raised) rather than a client input problem — the text being embedded
    is server-constructed (from already-validated product fields), the
    same reasoning as `EmbeddingGenerationException`. Hence a 500.
    """

    status_code = 500
    code = "text_embedding_error"
    message = "Failed to generate a text embedding."


class VectorStoreException(AppException):
    """A vector store operation (upsert, search, delete, or health check) failed.

    An infrastructure failure (Qdrant unreachable, a malformed collection,
    a client-library error) rather than a client input problem — the
    embedding being stored/searched has already been validated by the time
    this runs. Hence a 500, the same reasoning as `ChecksumException` and
    `EmbeddingGenerationException`.
    """

    status_code = 500
    code = "vector_store_error"
    message = "The vector store operation failed."
