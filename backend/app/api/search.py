"""Product search endpoint.

`POST /products/search` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/search`) accepts an
*optional* query image, an *optional* text query — at least one must be
given — and optional brand/category/price-range filters, as
`multipart/form-data`. Runs the request through the Phase 6 hybrid search
pipeline:

    UploadService.save_upload      -> validate + store the query file,
                                       only if one was given (Phase 2A)
    HybridSearchService.search     -> dispatches to image search, text
                                       search, or both plus weighted score
                                       fusion, depending on what was
                                       actually provided (Phase 6)

Mirrors `app/api/products.py`'s shape exactly: the router stays a thin
adapter — parse the request, delegate to both services in order, shape
the response — and never talks to the vector store or either individual
search service directly itself.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core import constants
from app.core.logging import get_logger
from app.dependencies.hybrid_search import get_hybrid_search_service
from app.dependencies.upload import get_upload_service
from app.models.search import ProductFilters
from app.schemas.product import ProductImage
from app.schemas.search import ProductSearchResponse, ProductSearchResult
from app.services.upload_service import UploadService
from app.services.vectorstore.hybrid_search_service import HybridSearchService

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "/search",
    response_model=ProductSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search for similar products by image, text, or both",
    description="Accepts an optional query image and/or an optional text query — at "
    "least one is required — plus optional brand/category/price-range filters, and "
    "returns the most similar previously uploaded products, ranked by similarity score. "
    "Providing both an image and text runs a weighted hybrid search across both.",
)
async def search_products(
    *,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    hybrid_search_service: Annotated[HybridSearchService, Depends(get_hybrid_search_service)],
    file: Annotated[UploadFile | None, File(description="Optional query image.")] = None,
    query: Annotated[str | None, Form(max_length=1000, description="Optional text query.")] = None,
    top_k: Annotated[
        int, Form(gt=0, le=constants.MAX_SEARCH_TOP_K)
    ] = constants.DEFAULT_SEARCH_TOP_K,
    brand: Annotated[str | None, Form(max_length=100)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    min_price: Annotated[float | None, Form(ge=0)] = None,
    max_price: Annotated[float | None, Form(ge=0)] = None,
) -> ProductSearchResponse:
    """Validate/store an optional query image, then run a hybrid search.

    Missing both `file` and `query` raises `ValidationException` (422,
    via `HybridSearchService`). Missing/invalid form fields, an
    unsupported file extension/MIME type, an oversized file, or an
    undecodable image are all handled by `UploadService`/`SearchService`
    (each raises the appropriate `AppException` subclass, converted to
    the standard error envelope by the global handlers) — this route
    stays a thin adapter.
    """
    logger.info(
        "Search request received: has_file=%s, has_query=%s, top_k=%d",
        file is not None and bool(file.filename),
        query is not None and query.strip() != "",
        top_k,
    )

    image: ProductImage | None = None
    if file is not None and file.filename:
        image = await upload_service.save_upload(file)

    filters = ProductFilters(
        brand=brand, category=category, min_price=min_price, max_price=max_price
    )
    results = await hybrid_search_service.search(
        image=image, text=query, top_k=top_k, filters=filters
    )

    return ProductSearchResponse(
        results=[
            ProductSearchResult(
                product_id=result.product_id,
                score=result.score,
                matched_modalities=[modality.value for modality in result.matched_modalities],
                metadata=result.metadata,
            )
            for result in results
        ]
    )
