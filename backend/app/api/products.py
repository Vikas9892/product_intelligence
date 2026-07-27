"""Product upload, duplicate-check, and recommendation endpoints.

`POST /products/upload` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/upload`) accepts product
metadata plus a single image file as `multipart/form-data`, and runs it
through the full Phase 2A + 2B + 3 + 4 + 6 + 7 + 8 pipeline:

    UploadService.save_upload      -> validate + store the file (Phase 2A)
    ProductService.process_upload  -> checksum, image processing
                                       (Phase 3, via ImageProcessingService),
                                       image + text embedding generation
                                       (Phases 4 and 6, via CLIPEmbeddingService
                                       and SentenceTransformerEmbeddingService),
                                       catalog intelligence enrichment (Phase 7),
                                       duplicate detection (Phase 8 — may raise
                                       ConflictException in BLOCK mode),
                                       normalize, validate, generate ID (2B)

Unlike `app/api/health.py`'s system routes (deliberately unversioned),
this is a real, versioned business endpoint, so it belongs under the
prefix — see the Phase 2A section of `backend/README.md`.

No database write happens here (this pipeline processes but does not
persist — that arrives in a later phase) — the response describes the
fully processed, normalized, identified, image-standardized upload, built
from `Product` (`app/models/product.py`), the internal domain object,
deliberately not returned directly (see that module's docstring).

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

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core.logging import get_logger
from app.dependencies.duplicate import get_duplicate_check_service
from app.dependencies.product import get_product_service
from app.dependencies.recommendation import get_recommendation_engine_service
from app.dependencies.upload import get_upload_service
from app.models.recommendation_type import RecommendationType
from app.schemas.duplicate import (
    DuplicateCandidateInfo,
    DuplicateCheckResponse,
    DuplicateSignalBreakdown,
)
from app.schemas.product import (
    DuplicateInfo,
    EmbeddingInfo,
    ProcessedImageInfo,
    ProductCreate,
    UploadResponse,
)
from app.schemas.recommendation import (
    RecommendationInfo,
    RecommendationReasonInfo,
    RecommendationsResponse,
)
from app.services.duplicate.duplicate_check_service import DuplicateCheckService
from app.services.product_service import ProductService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.upload_service import UploadService

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a product image",
    description="Accepts product metadata and a single image file, validates and "
    "stores the file, then processes it (checksum, metadata, "
    "normalization, ID generation). Does not persist a product record yet.",
)
async def upload_product(
    *,
    name: Annotated[str, Form(min_length=1, max_length=200, description="Product name.")],
    file: Annotated[UploadFile, File(description="The product image file.")],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    product_service: Annotated[ProductService, Depends(get_product_service)],
    brand: Annotated[str | None, Form(max_length=100)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    price: Annotated[float | None, Form(ge=0)] = None,
) -> UploadResponse:
    """Validate/store one product image, then process it into a `Product`.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    an oversized file, a blank-after-normalization name, or a checksum
    failure are all handled by `UploadService`/`ProductService` (each
    raises the appropriate `AppException` subclass, converted to the
    standard error envelope by the global handlers) — this route stays a
    thin adapter: parse the request, delegate to both services in order,
    shape the response.
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
    brand: Annotated[str | None, Form(max_length=100)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    top_k: Annotated[
        int | None, Form(gt=0, description="Overrides DUPLICATE_DETECTION__TOP_K for this call.")
    ] = None,
    threshold: Annotated[
        float | None,
        Form(ge=0, le=1, description="Overrides DUPLICATE_DETECTION__THRESHOLD for this call."),
    ] = None,
) -> DuplicateCheckResponse:
    """Validate/store the image (so it can be processed), then run duplicate detection only.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    or an invalid image are all handled by `UploadService`/
    `DuplicateCheckService` (each raises the appropriate `AppException`
    subclass) — this route stays a thin adapter, same as `upload_product`.
    """
    logger.info("Duplicate check requested: product_name=%s, filename=%s", name, file.filename)

    image = await upload_service.save_upload(file)
    decision = await duplicate_check_service.check(
        name=name,
        brand=brand,
        category=category,
        description=description,
        image=image,
        top_k=top_k,
        threshold=threshold,
    )

    best_candidate = decision.top_candidates[0] if decision.top_candidates else None
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
        duplicate=decision.is_duplicate,
        confidence=decision.confidence,
        reason=decision.reason,
        matched_product=decision.matched_product,
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
            for candidate in decision.top_candidates
        ],
    )


@router.get(
    "/{product_id}/recommendations",
    response_model=RecommendationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get recommendations for an already-uploaded product",
    description="Returns ranked recommendations for a product identified by ID, using its "
    "already-indexed embeddings and catalog metadata. 'similar' anchors on the full "
    "image+text profile; 'related' anchors on text/category alone.",
)
async def get_recommendations(
    product_id: UUID,
    recommendation_engine_service: Annotated[
        RecommendationEngineService, Depends(get_recommendation_engine_service)
    ],
    top_k: Annotated[int | None, Query(gt=0)] = None,
    recommendation_type: Annotated[RecommendationType, Query()] = RecommendationType.SIMILAR,
) -> RecommendationsResponse:
    """Look up `product_id`'s own stored embeddings and return ranked recommendations.

    Raises `ResourceNotFoundException` (404) if `product_id` isn't
    indexed — this route stays a thin adapter, same as every other route
    in this module.
    """
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
