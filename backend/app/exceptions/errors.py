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


class HybridSearchException(AppException):
    """A hybrid search's score-fusion step failed unexpectedly.

    `HybridSearchService` delegates image search to `SearchService`, text
    search to `TextSearchService`, and each already raises its own
    specific, meaningful exception on failure (`InvalidImageException`,
    `TextEmbeddingException`, `VectorStoreException`, ...) — those
    propagate as-is, unwrapped, since rewrapping an already-specific error
    would only lose information. This exception exists for the merge/
    fusion step itself: an infrastructure failure in code that has no
    client-input component to blame, the same reasoning as
    `VectorStoreException`. Hence a 500.
    """

    status_code = 500
    code = "hybrid_search_error"
    message = "Failed to combine image and text search results."


class CatalogIntelligenceException(AppException):
    """Catalog enrichment (attribute extraction, tag generation, or quality
    scoring) failed unexpectedly.

    An infrastructure failure in deterministic, server-side processing —
    not a client input problem — the product text/image being enriched
    has already been validated and processed by the time this runs. Hence
    a 500, the same reasoning as `HybridSearchException`.
    """

    status_code = 500
    code = "catalog_intelligence_error"
    message = "Failed to enrich the product with catalog intelligence."


class DuplicateDetectionException(AppException):
    """Duplicate detection (candidate retrieval or similarity scoring) failed unexpectedly.

    An infrastructure failure in deterministic, server-side processing —
    not a client input problem — the same reasoning as
    `CatalogIntelligenceException`. Hence a 500. Distinct from
    `ConflictException` (409), which is raised when duplicate detection
    *succeeds* and the result is "this looks like an existing product" —
    that's an expected business outcome in `BLOCK` mode, not a failure.
    """

    status_code = 500
    code = "duplicate_detection_error"
    message = "Failed to evaluate the product for duplicates."


class RecommendationException(AppException):
    """Recommendation generation (candidate retrieval, scoring, or diversity filtering)
    failed unexpectedly.

    An infrastructure failure in deterministic, server-side processing —
    not a client input problem — the same reasoning as
    `DuplicateDetectionException`. Hence a 500. Distinct from
    `ResourceNotFoundException` (404), which is raised when the *target*
    product itself isn't indexed — that's a client-addressable "this ID
    doesn't exist," not a processing failure.
    """

    status_code = 500
    code = "recommendation_error"
    message = "Failed to generate recommendations."


class EvaluationException(AppException):
    """Evaluation/benchmark execution failed unexpectedly.

    Covers both a malformed evaluation dataset (structurally invalid
    JSON, an entry that fails `EvaluationQuery` validation) and a failure
    while running an evaluated system (`HybridSearchService`,
    `DuplicateDetectionService`, `RecommendationEngineService`) or
    computing metrics. A 500 either way: the dataset is server-side
    fixture data, not per-request client input (unlike a malformed
    request body, which raises the existing `ValidationException`), and
    an evaluated system's own failure is exactly the same "infrastructure
    failure in deterministic, server-side processing" reasoning
    `RecommendationException`/`DuplicateDetectionException` already
    establish.
    """

    status_code = 500
    code = "evaluation_error"
    message = "Failed to run the evaluation."


class RerankException(AppException):
    """Cross-encoder reranking (model loading, inference, or the rerank pipeline itself)
    failed unexpectedly.

    An infrastructure failure in deterministic, server-side processing —
    not a client input problem — the same reasoning as
    `RecommendationException`/`DuplicateDetectionException`. Hence a 500.
    Callers that compose reranking as an *optional* refinement step
    (`HybridSearchService`, `RecommendationEngineService`,
    `DuplicateDetectionService`) let this propagate rather than silently
    falling back to unreranked results — a reranking failure should be
    visible, not hidden behind a quietly degraded response.
    """

    status_code = 500
    code = "rerank_error"
    message = "Failed to rerank candidates."


class JobException(AppException):
    """Job creation, queueing, or background processing failed unexpectedly.

    Covers `QueueManager`/`RedisQueue` failures (the queue backend itself
    is unreachable or returned something unexpected) and `ProductWorker`
    failures that exhausted all retries (moved to the dead-letter queue).
    A 500 either way — the same "infrastructure failure in deterministic,
    server-side processing" reasoning every other phase's own top-level
    exception already establishes. Distinct from `ResourceNotFoundException`
    (404), raised when a caller asks about a `job_id`/`product_id` that
    was never queued at all.
    """

    status_code = 500
    code = "job_error"
    message = "Failed to process the background job."


class ModelRegistryException(AppException):
    """The model registry failed unexpectedly — a misconfigured startup seed
    (a blank/invalid configured model name) or another internal failure that
    isn't one of the registry's own well-defined 404/409 cases.

    Looking up a version/active model that was never registered raises
    `ResourceNotFoundException` (404) instead, and registering a version
    that already exists raises `ConflictException` (409) — both reuse
    this codebase's existing generic exceptions rather than inventing
    registry-specific ones, the same "one flag, not two disagreeing ones"
    reasoning applied to error types here: a 404/409 is a 404/409
    regardless of which subsystem raised it.
    """

    status_code = 500
    code = "model_registry_error"
    message = "Failed to process the model registry request."


class DuplicateVerificationException(AppException):
    """Cross-encoder + business-rules duplicate verification failed unexpectedly (Phase 15).

    An infrastructure failure in deterministic, server-side processing —
    the reranking model failing, or combining the cross-encoder score with
    the business-rule signals raising unexpectedly — not a client input
    problem, the same reasoning as `DuplicateDetectionException`/
    `RerankException`. Hence a 500. Distinct from those two: this covers
    the *verification* orchestration specifically (`DuplicateVerificationService`),
    layered on top of the reranking and detection pipelines, each of which
    still raises its own `RerankException`/`DuplicateDetectionException`
    for its own failures.
    """

    status_code = 500
    code = "duplicate_verification_error"
    message = "Failed to verify whether the product is a duplicate."


class PricingException(AppException):
    """Pricing estimation failed unexpectedly (Phase 17).

    An infrastructure failure in deterministic, server-side processing —
    comparable retrieval raising, or aggregating the comparable prices
    failing unexpectedly — not a client input problem, the same reasoning
    every other phase's own top-level exception establishes. Hence a 500.
    Distinct from `ResourceNotFoundException` (404), raised when a
    `GET /pricing/{product_id}` names a product that isn't indexed: having
    *no priced comparables* is not an error (it yields a low-confidence,
    zero estimate), so it never raises this.
    """

    status_code = 500
    code = "pricing_error"
    message = "Failed to estimate a price."


class AuthenticationException(AppException):
    """A request to an enterprise-gated route presented no valid API key (Phase 19).

    A `401` — a missing, malformed, unknown, or revoked API key. Distinct
    from `AuthorizationException` (403): 401 means "we don't know who you
    are," 403 means "we know who you are, but you may not do this." Only
    raised when `ENTERPRISE__ENABLED` is on; with it off, no route requires
    a key.
    """

    status_code = 401
    code = "authentication_error"
    message = "A valid API key is required."


class AuthorizationException(AppException):
    """An authenticated key lacks the permission its target route requires (Phase 19).

    A `403` — the caller is known (a valid API key) but its `Role` doesn't
    grant the `Permission` the route asked for. Distinct from
    `AuthenticationException` (401): identity is established, authority is
    not.
    """

    status_code = 403
    code = "authorization_error"
    message = "You do not have permission to perform this action."


class QuotaExceededException(AppException):
    """A tenant exceeded its request quota or per-minute rate limit (Phase 19).

    A `429` — the tenant is over its `DAILY_REQUEST_QUOTA` or
    `RATE_LIMIT_PER_MINUTE`. A throttling signal, not a failure: the
    request was well-formed and authorized, just too frequent.
    """

    status_code = 429
    code = "quota_exceeded"
    message = "Request quota or rate limit exceeded."
