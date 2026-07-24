"""Product schemas: the data contracts for product upload and (eventually) persistence.

`ProductCreate`, `ProductImage`, and `UploadResponse` are in active use
today, by `POST /api/v1/products/upload` (`app/api/products.py`).
`ProductResponse` is not returned by any route yet — it's the shape a
persisted product will have once a later phase adds a database, defined
now so that phase's routes/tests don't have to invent the contract from
scratch, the same way Phase 1's `AIModelSettings` was reserved before any
AI call existed.

Deliberately separate from `app.models.product.Product` (Phase 2B's
internal domain model) — see that module's docstring and the Phase 2B
section of `backend/README.md` for why the two aren't the same type.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """Product metadata submitted alongside an image upload.

    Constructed by `app/api/products.py` from individual `Form(...)`
    parameters (not bound directly via `Annotated[ProductCreate, Form()]`
    — see that module's docstring for why combining a Form-model
    parameter with a `File()` upload doesn't spread fields the way it
    does in isolation), and again by `ProductService` to hold the
    normalized field values. Not parsed from a JSON body — a file upload
    and JSON can't share one request body, so the request is entirely
    `multipart/form-data`.
    """

    name: str = Field(min_length=1, max_length=200, description="Product name.")
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    price: float | None = Field(default=None, ge=0)


class ProductImage(BaseModel):
    """Metadata describing one image file `UploadService` has stored.

    `stored_filename` is a generated identifier, never the client-supplied
    `original_filename` — see `UploadService` for why (path-traversal /
    collision avoidance).
    """

    original_filename: str
    stored_filename: str
    content_type: str
    size_bytes: int = Field(gt=0)
    uploaded_at: datetime


class UploadResponse(BaseModel):
    """Response body for `POST /api/v1/products/upload`.

    No database row exists yet (Phase 2B processes but does not persist —
    see `backend/README.md`). `product_id` and `checksum_sha256` come from
    `app.models.product.Product`, the internal domain object
    `ProductService` builds; `product` reflects the *normalized* fields
    (trimmed, cased, sluggified, price-rounded), not the raw submitted
    values, since that's what was actually processed and would (in a
    later phase) be persisted.
    """

    product_id: UUID
    product: ProductCreate
    image: ProductImage
    checksum_sha256: str


class ProductResponse(BaseModel):
    """A persisted product, as it will be returned once storage exists.

    Reserved ahead of need (see module docstring) — not constructed by any
    route yet; `images` anticipates a product having more than one photo.
    """

    id: UUID
    name: str
    description: str | None
    category: str | None
    price: float | None
    images: list[ProductImage]
    created_at: datetime
