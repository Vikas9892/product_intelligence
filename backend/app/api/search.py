"""Product search endpoint.

`POST /products/search` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/search`) accepts a query
image as `multipart/form-data` and runs it through the Phase 5 search
pipeline:

    UploadService.save_upload      -> validate + store the query file (Phase 2A)
    SearchService.search_by_image  -> standardize, embed, and search for
                                       visually similar products (Phase 5)

Mirrors `app/api/products.py`'s shape exactly: the router stays a thin
adapter — parse the request, delegate to both services in order, shape
the response — and never talks to the vector store directly itself.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core import constants
from app.core.logging import get_logger
from app.dependencies.search import get_search_service
from app.dependencies.upload import get_upload_service
from app.models.search import ProductFilters
from app.schemas.search import ProductSearchResponse, ProductSearchResult
from app.services.upload_service import UploadService
from app.services.vectorstore.search_service import SearchService

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "/search",
    response_model=ProductSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search for visually similar products",
    description="Accepts a query image, embeds it, and returns the most visually "
    "similar previously uploaded products, ranked by similarity score.",
)
async def search_products(
    *,
    file: Annotated[UploadFile, File(description="The query image to search with.")],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    search_service: Annotated[SearchService, Depends(get_search_service)],
    top_k: Annotated[
        int, Form(gt=0, le=constants.MAX_SEARCH_TOP_K)
    ] = constants.DEFAULT_SEARCH_TOP_K,
    category: Annotated[str | None, Form(max_length=100)] = None,
) -> ProductSearchResponse:
    """Validate/store the query image, then search for visually similar products.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    an oversized file, or an undecodable image are all handled by
    `UploadService`/`SearchService` (each raises the appropriate
    `AppException` subclass, converted to the standard error envelope by
    the global handlers) — this route stays a thin adapter.
    """
    logger.info("Search request received: filename=%s, top_k=%d", file.filename, top_k)

    image = await upload_service.save_upload(file)
    filters = ProductFilters(category=category) if category is not None else None
    result = await search_service.search_by_image(image, top_k=top_k, filters=filters)

    return ProductSearchResponse(
        results=[
            ProductSearchResult(
                product_id=neighbor.product_id,
                score=neighbor.score,
                metadata=neighbor.metadata,
            )
            for neighbor in result.neighbors
        ]
    )
