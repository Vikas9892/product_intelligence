"""Decision-trace endpoints (Phase 16).

Explains, for an already-indexed product, the AI decisions the platform
makes about it:

- `GET /recommendations/{product_id}/trace` — why each recommended
  product was recommended.
- `GET /duplicates/{product_id}/trace` — the product's duplicate-decision
  trace.
- `GET /products/{product_id}/explanations` — both of the above combined
  into one explanation tree.

These are read-only: they run the *existing* by-product-id inference
(`RecommendationEngineService.recommend`,
`DuplicateDetectionService.detect_by_product_id`) and hand the results to
`ExplanationService` for explanation — the phase's own "explanation
generation must not affect inference results" requirement (the same
inference runs whether or not it's being explained). Thin adapters, same
as every other route: delegate, shape the response.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.duplicate import get_duplicate_detection_service
from app.dependencies.explanations import get_explanation_service
from app.dependencies.recommendation import get_recommendation_engine_service
from app.schemas.explanation import (
    ExplanationResponse,
    ProductExplanationsResponse,
    TraceBundleResponse,
)
from app.services.duplicate.duplicate_check_service import decision_to_verification
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.explanations.explanation_service import ExplanationService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService

logger = get_logger(__name__)

router = APIRouter(tags=["explanations"])


async def _recommendation_traces(
    product_id: UUID,
    recommendation_engine_service: RecommendationEngineService,
    explanation_service: ExplanationService,
) -> list[ExplanationResponse]:
    result = await recommendation_engine_service.recommend(product_id=product_id)
    return [
        ExplanationResponse.from_trace(explanation_service.explain_recommendation(candidate))
        for candidate in result.recommendations
    ]


async def _duplicate_trace(
    product_id: UUID,
    duplicate_detection_service: DuplicateDetectionService,
    explanation_service: ExplanationService,
) -> ExplanationResponse:
    decision = await duplicate_detection_service.detect_by_product_id(product_id)
    verification = decision_to_verification(decision)
    return ExplanationResponse.from_trace(explanation_service.explain_duplicate(verification))


@router.get(
    "/recommendations/{product_id}/trace",
    response_model=TraceBundleResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain a product's recommendations",
    description="Returns one explanation trace per recommended product — why each was recommended.",
)
async def recommendation_trace(
    product_id: UUID,
    recommendation_engine_service: Annotated[
        RecommendationEngineService, Depends(get_recommendation_engine_service)
    ],
    explanation_service: Annotated[ExplanationService, Depends(get_explanation_service)],
) -> TraceBundleResponse:
    """Explain each of `product_id`'s recommendations.

    Raises `ResourceNotFoundException` (404) if `product_id` isn't indexed
    (propagated from `RecommendationEngineService`).
    """
    traces = await _recommendation_traces(
        product_id, recommendation_engine_service, explanation_service
    )
    logger.info("Recommendation trace requested: product_id=%s, traces=%d", product_id, len(traces))
    return TraceBundleResponse(subject_id=str(product_id), count=len(traces), traces=traces)


@router.get(
    "/duplicates/{product_id}/trace",
    response_model=ExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain a product's duplicate decision",
    description="Returns the explanation trace for whether the product looks like a duplicate.",
)
async def duplicate_trace(
    product_id: UUID,
    duplicate_detection_service: Annotated[
        DuplicateDetectionService, Depends(get_duplicate_detection_service)
    ],
    explanation_service: Annotated[ExplanationService, Depends(get_explanation_service)],
) -> ExplanationResponse:
    """Explain `product_id`'s duplicate decision.

    Raises `ResourceNotFoundException` (404) if `product_id` isn't indexed
    (propagated from `DuplicateDetectionService`).
    """
    trace = await _duplicate_trace(product_id, duplicate_detection_service, explanation_service)
    logger.info("Duplicate trace requested: product_id=%s", product_id)
    return trace


@router.get(
    "/products/{product_id}/explanations",
    response_model=ProductExplanationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Explain every AI decision about a product",
    description="Combines the product's duplicate-decision trace and its recommendation "
    "traces into one explanation tree.",
)
async def product_explanations(
    product_id: UUID,
    recommendation_engine_service: Annotated[
        RecommendationEngineService, Depends(get_recommendation_engine_service)
    ],
    duplicate_detection_service: Annotated[
        DuplicateDetectionService, Depends(get_duplicate_detection_service)
    ],
    explanation_service: Annotated[ExplanationService, Depends(get_explanation_service)],
) -> ProductExplanationsResponse:
    """Explain both the duplicate decision and the recommendations for `product_id`.

    Raises `ResourceNotFoundException` (404) if `product_id` isn't indexed.
    """
    duplicate = await _duplicate_trace(product_id, duplicate_detection_service, explanation_service)
    recommendations = await _recommendation_traces(
        product_id, recommendation_engine_service, explanation_service
    )
    logger.info(
        "Product explanations requested: product_id=%s, recommendations=%d",
        product_id,
        len(recommendations),
    )
    return ProductExplanationsResponse(
        product_id=str(product_id), duplicate=duplicate, recommendations=recommendations
    )
