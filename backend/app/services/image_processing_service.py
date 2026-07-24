"""Image processing service: turns a stored upload into a standardized image.

`ImageProcessingService.process_image` orchestrates, in order: validate
the file is a genuine, appropriately-sized image (`ImageValidator`), fix
its display orientation, convert it to plain RGB, resize it to the
configured standard size (the `app.utils.image` functions), and save the
result as a new file — returning `ImageMetadata` describing what was
produced. This is the step that makes AI models (CLIP, DINOv2, ...) see a
consistent input regardless of what a client actually uploaded (PNG vs.
JPEG, portrait EXIF rotation, an alpha channel, an oversized photo, ...).

Like `UploadService`/`ChecksumService`, all Pillow calls are blocking and
therefore run inside a thread pool (`run_in_threadpool`) so they don't
block the event loop; the transformation functions themselves
(`app.utils.image`) stay synchronous, since only this service's methods
need to be `async`.
"""

from pathlib import Path

from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.core import constants
from app.core.config import settings
from app.core.logging import get_logger
from app.models.image_metadata import ImageMetadata
from app.utils.image import (
    apply_orientation,
    generate_processed_filename,
    normalize_color_mode,
    resize_preserving_aspect_ratio,
)
from app.validators.image_validator import ImageValidator

logger = get_logger(__name__)

# A high-quality setting appropriate for a one-time standardization step
# feeding AI models, not a repeatedly-recompressed user-facing asset.
_JPEG_QUALITY = 90


class ImageProcessingService:
    """Validates, normalizes, and resizes a stored image into a standard format."""

    def __init__(
        self,
        *,
        processed_dir: Path | None = None,
        max_output_dimension_px: int | None = None,
        validator: ImageValidator | None = None,
    ) -> None:
        self._processed_dir = (
            processed_dir if processed_dir is not None else settings.storage.processed_dir
        )
        self._max_output_dimension_px = (
            max_output_dimension_px
            if max_output_dimension_px is not None
            else settings.storage.processed_image_size_px
        )
        self._validator = validator if validator is not None else ImageValidator()

        # Belt-and-suspenders: `app/lifespan.py` ensures this exists at
        # real application startup (see `app.core.paths`); repeating it
        # here means the service is self-sufficient for direct/unit-test
        # use too, the same reasoning `UploadService` already follows.
        self._processed_dir.mkdir(parents=True, exist_ok=True)

    async def process_image(self, original_path: Path, stored_filename: str) -> ImageMetadata:
        """Validate and standardize the image at `original_path`.

        `stored_filename` is used only to derive the processed file's
        name (see `app.utils.image.generate_processed_filename`) and for
        log messages — it's already a server-generated identifier (see
        `UploadService`), not client-controlled input.

        Raises whatever `ImageValidator.validate` raises
        (`InvalidImageException`, `UnsupportedMediaTypeException`, or
        `ImageTooLargeException`) if the file doesn't pass validation;
        processing never runs on a file that failed it.
        """
        logger.info("Image processing started: filename=%s", stored_filename)

        width, height, image_format = await run_in_threadpool(
            self._validator.validate, original_path
        )
        logger.info(
            "Image verified: filename=%s, format=%s, dimensions=%dx%d",
            stored_filename,
            image_format,
            width,
            height,
        )

        processed_filename = generate_processed_filename(stored_filename)
        processed_path = self._processed_dir / processed_filename

        final_width, final_height, color_mode = await run_in_threadpool(
            self._transform_and_save, original_path, processed_path
        )
        logger.info(
            "Image processed: filename=%s, output=%s, dimensions=%dx%d",
            stored_filename,
            processed_filename,
            final_width,
            final_height,
        )

        return ImageMetadata(
            width=final_width,
            height=final_height,
            format=constants.PROCESSED_IMAGE_FORMAT,
            color_mode=color_mode,
            original_path=original_path,
            processed_path=processed_path,
        )

    def _transform_and_save(
        self, original_path: Path, processed_path: Path
    ) -> tuple[int, int, str]:
        """Apply orientation, normalize color mode, resize, and save. Returns (width, height, mode)."""
        with Image.open(original_path) as opened_image:
            # Explicitly widened to `Image.Image`: each transformation
            # below may return a new image of that base type, which a
            # variable still typed as `Image.open`'s more specific
            # `ImageFile` return type couldn't be reassigned to.
            image: Image.Image = opened_image
            image = apply_orientation(image)
            image = normalize_color_mode(image)
            image = resize_preserving_aspect_ratio(
                image, max_dimension=self._max_output_dimension_px
            )
            image.save(
                processed_path, format=constants.PROCESSED_IMAGE_FORMAT, quality=_JPEG_QUALITY
            )
            return image.width, image.height, image.mode
