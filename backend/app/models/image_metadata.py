"""Internal domain model: `ImageMetadata`, describing one processed image file.

Separate from `app.schemas.product` (the API contract) for the same
reason `app.models.product.Product` is: this carries information — most
importantly `original_path`/`processed_path`, real filesystem paths —
that must never leak into an HTTP response (see Phase 2A's rationale for
keeping server paths out of API-facing schemas). `app/api/products.py`
maps the API-safe subset of this (width, height, format, color_mode) onto
a response schema; the paths stay internal.

Built exclusively by `ImageProcessingService`
(`app/services/image_processing_service.py`) and attached to `Product`
(`app/models/product.py`) as `Product.image_metadata`.
"""

from pathlib import Path

from pydantic import BaseModel, Field


class ImageMetadata(BaseModel):
    """Dimensions, format, and file locations for one processed image."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    color_mode: str
    original_path: Path
    processed_path: Path
