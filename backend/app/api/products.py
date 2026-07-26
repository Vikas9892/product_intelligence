"""Product upload endpoint.

`POST /products/upload` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/upload`) accepts product
metadata plus a single image file as `multipart/form-data`, and runs it
through the full Phase 2A + 2B + 3 + 4 + 6 pipeline:

    UploadService.save_upload      -> validate + store the file (Phase 2A)
    ProductService.process_upload  -> checksum, image processing
                                       (Phase 3, via ImageProcessingService),
                                       image + text embedding generation
                                       (Phases 4 and 6, via CLIPEmbeddingService
                                       and SentenceTransformerEmbeddingService),
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

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.logging import get_logger
from app.dependencies.product import get_product_service
from app.dependencies.upload import get_upload_service
from app.schemas.product import EmbeddingInfo, ProcessedImageInfo, ProductCreate, UploadResponse
from app.services.product_service import ProductService
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
    )
