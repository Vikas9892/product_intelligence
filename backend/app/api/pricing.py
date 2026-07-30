"""Pricing intelligence endpoints (Phase 17).

`POST /pricing/estimate` (mounted under `settings.application.api_prefix`,
so `/api/v1/pricing/estimate`) estimates a fair market price for a
*described* (not-yet-indexed) product from a JSON body;
`GET /pricing/{product_id}` prices an *already-indexed* product by ID,
reusing its stored embedding. Both return the same `PricingResponse`
(estimated price, confidence band + score, the comparables used, and a
human-readable `pricing_reason`).

Thin adapters, same as every other route: delegate to the
`BasePricingService`, shape the response. The whole router is registered
only when `PRICING__ENABLED` is on.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.pricing import get_pricing_service
from app.schemas.pricing import PricingRequest, PricingResponse
from app.services.pricing.base_pricing_service import BasePricingService

logger = get_logger(__name__)

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.post(
    "/estimate",
    response_model=PricingResponse,
    status_code=status.HTTP_200_OK,
    summary="Estimate a fair price for a described product",
    description="Estimates a fair market price for a product described by name/brand/"
    "category/description, from semantically similar priced products.",
)
async def estimate_price(
    request: PricingRequest,
    pricing_service: Annotated[BasePricingService, Depends(get_pricing_service)],
) -> PricingResponse:
    """Estimate a fair price for the described product.

    Raises whatever the pricing service raises for retrieval failures
    (`PricingException`, or an underlying search error) — this route stays
    a thin adapter.
    """
    estimate = await pricing_service.estimate_for_request(
        name=request.name,
        brand=request.brand,
        category=request.category,
        description=request.description,
        top_k=request.top_k,
    )
    logger.info(
        "Price estimate requested: name=%s, price=%.2f, confidence=%s",
        request.name,
        estimate.estimated_price,
        estimate.confidence.value,
    )
    return PricingResponse.from_estimate(estimate)


@router.get(
    "/{product_id}",
    response_model=PricingResponse,
    status_code=status.HTTP_200_OK,
    summary="Estimate a fair price for an indexed product",
    description="Estimates a fair market price for an already-indexed product, by ID.",
)
async def price_indexed_product(
    product_id: UUID,
    pricing_service: Annotated[BasePricingService, Depends(get_pricing_service)],
) -> PricingResponse:
    """Estimate a fair price for `product_id`.

    Raises `ResourceNotFoundException` (404) if `product_id` isn't indexed
    (propagated from the pricing service's comparable retrieval).
    """
    estimate = await pricing_service.estimate_for_product(product_id)
    logger.info(
        "Indexed-product price requested: product_id=%s, price=%.2f, confidence=%s",
        product_id,
        estimate.estimated_price,
        estimate.confidence.value,
    )
    return PricingResponse.from_estimate(estimate)
