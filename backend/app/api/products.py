"""Product upload endpoint.

`POST /products/upload` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/products/upload`) accepts product
metadata plus a single image file as `multipart/form-data`, delegates all
validation and storage to `UploadService`, and returns metadata about what
was stored. Unlike `app/api/health.py`'s system routes (deliberately
unversioned), this is a real, versioned business endpoint, so it belongs
under the prefix — see the Phase 2A section of `backend/README.md`.

No database write happens here (Phase 2A is upload-only by design) — the
response describes the accepted upload, not a persisted `Product` row;
that arrives in a later phase.

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
from app.dependencies.upload import get_upload_service
from app.schemas.product import ProductCreate, UploadResponse
from app.services.upload_service import UploadService

logger = get_logger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a product image",
    description="Accepts product metadata and a single image file, validates the "
    "file (extension, MIME type, size), and stores it. Does not persist "
    "a product record yet.",
)
async def upload_product(
    *,
    name: Annotated[str, Form(min_length=1, max_length=200, description="Product name.")],
    file: Annotated[UploadFile, File(description="The product image file.")],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    description: Annotated[str | None, Form(max_length=2000)] = None,
    category: Annotated[str | None, Form(max_length=100)] = None,
    price: Annotated[float | None, Form(ge=0)] = None,
) -> UploadResponse:
    """Validate and store one product image, alongside its product metadata.

    Missing/invalid form fields, an unsupported file extension/MIME type,
    and an oversized file are all `UploadService`'s responsibility (it
    raises the appropriate `AppException` subclass, converted to the
    standard error envelope by the global handlers) — this route stays a
    thin adapter: parse the request, delegate, shape the response.
    """
    product = ProductCreate(name=name, description=description, category=category, price=price)
    logger.info(
        "Upload request received: product_name=%s, filename=%s",
        product.name,
        file.filename,
    )

    image = await upload_service.save_upload(file)

    logger.info(
        "Upload stored: product_name=%s, stored_filename=%s, size_bytes=%d",
        product.name,
        image.stored_filename,
        image.size_bytes,
    )

    return UploadResponse(product=product, image=image)
