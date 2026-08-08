"""Product upload, duplicate-check, status, and recommendation endpoints.

`POST /products/upload` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/upload`) accepts product
metadata plus a single image file as `multipart/form-data`. Its behavior
depends on `settings.async_pipeline.enabled` (Phase 12, on by default):

- **Enabled (the default):** `UploadService.save_upload` validates and
  stores the file, a `Job` is created and queued (`QueueManager`), and
  the route returns `202 Accepted` immediately (`UploadAcceptedResponse`)
  — the full pipeline (checksum, image processing, embeddings, catalog
  intelligence, duplicate detection, vector indexing, recommendation
  cache warm-up) runs later, in a separate `ProductWorker` process (see
  `app/workers/product_worker.py`). `GET /products/{id}/status` (this
  module) and `GET /jobs/{job_id}` (`app/api/jobs.py`) poll progress.
- **Disabled:** the pre-Phase-12 fully-synchronous behavior — this route
  calls `ProductService.process_upload` directly and returns `201
  Created` with the complete `UploadResponse` in the same request, for
  simple local dev without Redis running.

Unlike `app/api/health.py`'s system routes (deliberately unversioned),
this is a real, versioned business endpoint, so it belongs under the
prefix — see the Phase 2A section of `backend/README.md`.

No database write happens here (Phase 12 uses Redis for job/status
tracking, not a relational database — see that phase's own README
section) — the response describes the queued (or, synchronously,
fully processed) upload, built from `Product`
(`app/models/product.py`), the internal domain object, deliberately not
returned directly (see that module's docstring).

**Why individual `Form(...)` parameters instead of
`Annotated[ProductCreate, Form()]`?** FastAPI's "Form models" feature
normally spreads a `Form()`-annotated Pydantic model's fields as flat
top-level form fields. But as soon as a *second* body parameter is also
present — here, the `File()` upload — FastAPI switches to "embedded"
mode, expecting the whole model nested under one key (`product`) instead
of flat fields, which is neither how HTML forms nor most HTTP clients
send multipart data alongside a file. Accepting each field individually
(mirroring `ProductCreate`'s constraints on the `Form(...)` declarations
below) keeps the wire format flat and avoids that quirk; `ProductCreate`
itself stays the canonical schema, constructed from the validated
individual fields.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.dependencies.analytics import get_analytics_repository
from app.dependencies.duplicate import get_duplicate_check_service
from app.dependencies.product import (
    get_product_image_service,
    get_product_lookup_service,
    get_product_service,
)
from app.dependencies.queue import get_queue_manager
from app.dependencies.recommendation import (
    get_recommendation_cache_repository,
    get_recommendation_engine_service,
)
from app.dependencies.upload import get_upload_service
from app.exceptions.errors import ResourceNotFoundException
from app.jobs.base_job import Job
from app.models.analytics_event import AnalyticsEvent
from app.models.recommendation_type import RecommendationType
from app.queue.queue_manager import QueueManager
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.recommendation_cache_repository import RecommendationCacheRepository
from app.schemas.duplicate import (
    DuplicateCandidateInfo,
    DuplicateCheckResponse,
    DuplicateSignalBreakdown,
)
from app.schemas.job import JobStatusResponse
from app.schemas.product import (
    DuplicateInfo,
    EmbeddingInfo,
    ProcessedImageInfo,
    ProductCreate,
    ProductImage,
    UploadAcceptedResponse,
    UploadResponse,
)
from app.schemas.product_summary import (
    MAX_BATCH_SIZE,
    ProductBatchRequest,
    ProductBatchResponse,
    ProductSummary,
)
from app.schemas.recommendation import (
    RecommendationInfo,
    RecommendationReasonInfo,
    RecommendationsResponse,
)
from app.services.duplicate.duplicate_check_service import DuplicateCheckService
from app.services.product_image_service import (
    ProductImageNotFoundError,
    ProductImageService,
)
from app.services.product_lookup_service import ProductLookupService
from app.services.product_service import ProductService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.upload_service import UploadService
from app.workers.product_worker import build_product_processing_payload

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "/upload",
    response_model=UploadResponse | UploadAcceptedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a product image",
    description="Accepts product metadata and a single image file, validates and stores "
    "the file, then either queues it for background processing (202 Accepted, the "
    "default) or processes it synchronously in this same request (201 Created) "
    "depending on ASYNC_PIPELINE__ENABLED.",
)
async def upload_product(
    *,
    name: Annotated[str, Form(min_length=1, max_length=200, description="Product name.")],
    file: Annotated[UploadFile, File(description="The product image file.")],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    product_service: Annotated[ProductService, Depends(get_product_service)],
    queue_manager: Annotated[QueueManager, Depends(get_queue_manager)],
    analytics_repository: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
    response: Response,
    brand: Annotated[str | None, Form(max_length=100)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    price: Annotated[float | None, Form(ge=0)] = None,
) -> UploadResponse | UploadAcceptedResponse:
    """Validate/store one product image, then either queue it or process it into a `Product`.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    an oversized file, a blank-after-normalization name, or a checksum
    failure are all handled by `UploadService`/`ProductService` (each
    raises the appropriate `AppException` subclass, converted to the
    standard error envelope by the global handlers) — this route stays a
    thin adapter: parse the request, delegate to both services (plus
    `QueueManager` in async mode) in order, shape the response.
    """
    product_input = ProductCreate(
        name=name, brand=brand, description=description, category=category, price=price
    )
    logger.info(
        "Upload request received: product_name=%s, filename=%s",
        product_input.name,
        file.filename,
    )

    image = await upload_service.save_upload(file)
    await analytics_repository.record_event(AnalyticsEvent.UPLOAD)

    if settings.async_pipeline.enabled:
        return await _queue_for_processing(product_input, image, queue_manager, response)

    product = await product_service.process_upload(product_input, image)

    return UploadResponse(
        product_id=product.id,
        product=ProductCreate(
            name=product.name,
            brand=product.brand,
            description=product.description,
            category=product.category,
            price=product.price,
        ),
        image=image,
        checksum_sha256=product.file_metadata.checksum_sha256,
        processed_image=ProcessedImageInfo(
            width=product.image_metadata.width,
            height=product.image_metadata.height,
            format=product.image_metadata.format,
            color_mode=product.image_metadata.color_mode,
        ),
        embedding=EmbeddingInfo(
            model_name=product.embedding.model_name,
            dimension=product.embedding.embedding_dimension,
        ),
        duplicate=DuplicateInfo(
            is_duplicate=product.duplicate_decision.is_duplicate,
            confidence=product.duplicate_decision.confidence,
            reason=product.duplicate_decision.reason,
            matched_product=product.duplicate_decision.matched_product,
        ),
    )


async def _queue_for_processing(
    product_input: ProductCreate,
    image: ProductImage,
    queue_manager: QueueManager,
    response: Response,
) -> UploadAcceptedResponse:
    """Create and enqueue a `PRODUCT_PROCESSING` job for `product_input`/`image`.

    Pre-assigns `product_id` here (before any processing happens) so it
    can be returned to the caller immediately, and so a retried job
    reuses that same ID across every attempt — see
    `ProductService.process_upload`'s own docstring for why that makes
    retries idempotent.
    """
    product_id = uuid.uuid4()
    now = datetime.now(UTC)
    job = Job(
        job_id=uuid.uuid4(),
        product_id=product_id,
        payload=build_product_processing_payload(product_input, image),
        created_at=now,
        updated_at=now,
        max_retries=settings.async_pipeline.max_retries,
    )
    await queue_manager.enqueue(job)
    logger.info(
        "Upload queued for background processing: job_id=%s, product_id=%s",
        job.job_id,
        product_id,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return UploadAcceptedResponse(
        product_id=product_id,
        job_id=job.job_id,
        status=job.status.value,
        status_url=f"{settings.application.api_prefix}/products/{product_id}/status",
    )


@router.post(
    "/check-duplicate",
    response_model=DuplicateCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check whether a product would be a duplicate",
    description="Accepts product metadata and a single image file and reports whether "
    "it looks like a duplicate of an existing product. Never stores or indexes "
    "anything (Phase 8) — for that, use POST /products/upload with "
    "DUPLICATE_DETECTION__MODE=warn or block.",
)
async def check_duplicate(
    *,
    name: Annotated[str, Form(min_length=1, max_length=200, description="Product name.")],
    file: Annotated[UploadFile, File(description="The product image file.")],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    duplicate_check_service: Annotated[DuplicateCheckService, Depends(get_duplicate_check_service)],
    analytics_repository: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
    brand: Annotated[str | None, Form(max_length=100)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    price: Annotated[
        float | None,
        Form(ge=0, description="Product price, used by cross-encoder verification's price rule."),
    ] = None,
    top_k: Annotated[
        int | None, Form(gt=0, description="Overrides DUPLICATE_DETECTION__TOP_K for this call.")
    ] = None,
    threshold: Annotated[
        float | None,
        Form(ge=0, le=1, description="Overrides DUPLICATE_DETECTION__THRESHOLD for this call."),
    ] = None,
) -> DuplicateCheckResponse:
    """Validate/store the image (so it can be processed), then run duplicate detection/verification.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    or an invalid image are all handled by `UploadService`/
    `DuplicateCheckService` (each raises the appropriate `AppException`
    subclass) — this route stays a thin adapter, same as `upload_product`.
    The `cross_encoder_score`/`retrieval_similarity`/`reasons` response
    fields are populated only when `DUPLICATE_VERIFICATION__ENABLED` is on
    (Phase 15); otherwise the response is exactly the pre-Phase-15 shape.
    """
    logger.info("Duplicate check requested: product_name=%s, filename=%s", name, file.filename)

    await analytics_repository.record_event(AnalyticsEvent.DUPLICATE_CHECK)
    image = await upload_service.save_upload(file)
    verification = await duplicate_check_service.check(
        name=name,
        brand=brand,
        category=category,
        description=description,
        image=image,
        price=price,
        top_k=top_k,
        threshold=threshold,
    )

    best_candidate = verification.top_candidates[0] if verification.top_candidates else None
    signals = (
        DuplicateSignalBreakdown(
            image=best_candidate.image_similarity,
            text=best_candidate.text_similarity,
            metadata=best_candidate.metadata_similarity,
            attribute=best_candidate.attribute_similarity,
        )
        if best_candidate is not None
        else None
    )

    return DuplicateCheckResponse(
        duplicate=verification.is_duplicate,
        confidence=verification.confidence,
        reason=verification.reasons[0].message if verification.reasons else "",
        matched_product=verification.matched_product,
        signals=signals,
        top_candidates=[
            DuplicateCandidateInfo(
                product_id=candidate.product_id,
                image_similarity=candidate.image_similarity,
                text_similarity=candidate.text_similarity,
                metadata_similarity=candidate.metadata_similarity,
                attribute_similarity=candidate.attribute_similarity,
                overall_similarity=candidate.overall_similarity,
            )
            for candidate in verification.top_candidates
        ],
        cross_encoder_score=verification.cross_encoder_score,
        retrieval_similarity=verification.retrieval_similarity,
        reasons=[reason.message for reason in verification.reasons],
    )


@router.get(
    "/{product_id}/status",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a product's background-processing status",
    description="Returns the status/progress/current stage of the background job "
    "processing this product (Phase 12). The counterpart to GET /jobs/{job_id}, "
    "looked up by product_id instead of job_id.",
)
async def get_product_status(
    product_id: UUID, queue_manager: Annotated[QueueManager, Depends(get_queue_manager)]
) -> JobStatusResponse:
    """Look up the job queued for `product_id`.

    Raises `ResourceNotFoundException` (404) if no job was ever queued
    for `product_id` — this route stays a thin adapter, same as every
    other route in this module.
    """
    job = await queue_manager.get_by_product_id(product_id)
    if job is None:
        raise ResourceNotFoundException(
            f"No job found for product '{product_id}'.", resource="product"
        )

    logger.info(
        "Product status requested: product_id=%s, job_id=%s, status=%s",
        product_id,
        job.job_id,
        job.status.value,
    )
    return JobStatusResponse.from_job(job)


@router.get(
    "/{product_id}/recommendations",
    response_model=RecommendationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recommendations for an already-uploaded product",
    description="Returns ranked recommendations for a product identified by ID, using its "
    "already-indexed embeddings and catalog metadata (or a worker-precomputed cache "
    "entry, Phase 12). 'similar' anchors on the full image+text profile; 'related' "
    "anchors on text/category alone.",
)
async def get_recommendations(
    product_id: UUID,
    recommendation_engine_service: Annotated[
        RecommendationEngineService, Depends(get_recommendation_engine_service)
    ],
    recommendation_cache_repository: Annotated[
        RecommendationCacheRepository, Depends(get_recommendation_cache_repository)
    ],
    analytics_repository: Annotated[AnalyticsRepository, Depends(get_analytics_repository)],
    top_k: Annotated[int | None, Query(gt=0)] = None,
    recommendation_type: Annotated[RecommendationType, Query()] = RecommendationType.SIMILAR,
) -> RecommendationsResponse:
    """Look up `product_id`'s own stored embeddings and return ranked recommendations.

    Checks `RecommendationCacheRepository` first — but only for a plain
    default request (`recommendation_type=SIMILAR`, no `top_k` override)
    — `ProductWorker` only ever warms the cache with those defaults, so
    a customized request always computes live rather than risk returning
    a cached result that doesn't match what was actually asked for.
    Raises `ResourceNotFoundException` (404) if `product_id` isn't
    indexed — this route stays a thin adapter, same as every other route
    in this module.
    """
    await analytics_repository.record_event(AnalyticsEvent.RECOMMENDATION)
    result = None
    if recommendation_type is RecommendationType.SIMILAR and top_k is None:
        result = await recommendation_cache_repository.get(product_id)

    if result is None:
        result = await recommendation_engine_service.recommend(
            product_id=product_id, recommendation_type=recommendation_type, top_k=top_k
        )

    return RecommendationsResponse(
        recommendation_type=result.recommendation_type.value,
        recommendations=[
            RecommendationInfo(
                product_id=recommendation.product_id,
                score=recommendation.final_score,
                reason=RecommendationReasonInfo(
                    matched_attributes=recommendation.reason.matched_attributes,
                    matched_tags=recommendation.reason.shared_tags,
                    shared_brand=recommendation.reason.shared_brand,
                    shared_category=recommendation.reason.shared_category,
                ),
                explanation=recommendation.explanation,
            )
            for recommendation in result.recommendations
        ],
    )


@router.get(
    "/{product_id}",
    response_model=ProductSummary,
    status_code=status.HTTP_200_OK,
    summary="Get an indexed product's catalog metadata",
    description="Resolves a product ID to the metadata stored alongside its vectors — "
    "name, brand, category, price, extracted attributes, tags and quality score. "
    "Recommendations, duplicate decisions and explanations all return bare product "
    "IDs; this is how a client turns one back into a product.",
)
async def get_product(
    product_id: UUID,
    lookup_service: Annotated[ProductLookupService, Depends(get_product_lookup_service)],
) -> ProductSummary:
    """Return `product_id`'s stored catalog metadata.

    Raises `ResourceNotFoundException` (404) when the product is not
    indexed — a real, distinguishable state, so a client can render
    "product not found" rather than an ambiguous placeholder.
    """
    summary = await lookup_service.get(product_id)
    if summary is None:
        raise ResourceNotFoundException(
            f"Product '{product_id}' is not indexed.", resource="product"
        )
    logger.info("Product resolved: product_id=%s", product_id)
    return summary


@router.post(
    "/batch",
    response_model=ProductBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve several product IDs at once",
    description="Resolves up to "
    f"{MAX_BATCH_SIZE} product IDs in one round trip, for views that render many "
    "products at once (a recommendation list, a set of duplicate candidates). "
    "Unknown IDs are returned in `missing` rather than failing the request, so a "
    "partially-stale list still renders what exists.",
)
async def get_products_batch(
    request: ProductBatchRequest,
    lookup_service: Annotated[ProductLookupService, Depends(get_product_lookup_service)],
) -> ProductBatchResponse:
    """Resolve `request.product_ids` to summaries.

    Over-sized batches are rejected by the schema's `max_length` as a 422
    validation error, carrying the offending field — consistent with every
    other malformed request in this API rather than a bespoke 400.
    """
    found, missing = await lookup_service.get_many(request.product_ids)
    return ProductBatchResponse(products=found, missing=missing, resolved_at=datetime.now(UTC))


@router.get(
    "/{product_id}/image",
    status_code=status.HTTP_200_OK,
    response_class=FileResponse,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "The product's stored image."},
        404: {"description": "The product has no stored image."},
    },
    summary="Get a product's stored image",
    description="Returns the standardized (processed) image for a product. Pass "
    "`thumbnail=true` for a small variant suitable for cards and result lists. "
    "Returns 404 when the product carries no stored image — distinct from the "
    "product not existing.",
)
async def get_product_image(
    product_id: UUID,
    image_service: Annotated[ProductImageService, Depends(get_product_image_service)],
    thumbnail: Annotated[
        bool, Query(description="Return a small variant instead of the full image.")
    ] = False,
) -> FileResponse:
    """Serve `product_id`'s stored image.

    The filesystem path is resolved server-side from the product's own
    record — never from anything the client supplies — and validated to
    stay inside the configured storage root. See `ProductImageService`.
    """
    try:
        resolved = await image_service.resolve(product_id, thumbnail=thumbnail)
    except ProductImageNotFoundError as exc:
        raise ResourceNotFoundException(str(exc), resource="product_image") from exc

    logger.info(
        "Product image served: product_id=%s, thumbnail=%s, file=%s",
        product_id,
        thumbnail,
        resolved.path.name,
    )
    return FileResponse(
        resolved.path,
        media_type=resolved.media_type,
        headers={"Cache-Control": resolved.cache_control},
    )
