"""Image validation: is this stored file a genuine, undamaged, acceptable image?

Runs *after* `UploadService`/`app.validators.file_validator` have already
accepted a file based on its filename extension and declared
`Content-Type` — both are client-supplied and prove nothing about the
file's actual bytes. `ImageValidator` is the check that doesn't trust
either: it asks Pillow to actually decode the file and only proceeds if
that succeeds.

A blocking, synchronous class — like `app.validators.file_validator`'s
functions, this does no I/O-await of its own. `ImageProcessingService`
(async) is responsible for running `validate()` inside a thread pool so
it doesn't block the event loop.
"""

from pathlib import Path

from PIL import Image

from app.core import constants
from app.core.config import settings
from app.exceptions.errors import (
    ImageTooLargeException,
    InvalidImageException,
    UnsupportedMediaTypeException,
)


class ImageValidator:
    """Verifies a stored file is a genuine, undamaged, appropriately-sized image."""

    def __init__(
        self,
        *,
        max_dimension_px: int | None = None,
        allowed_formats: frozenset[str] | None = None,
    ) -> None:
        self._max_dimension_px = (
            max_dimension_px
            if max_dimension_px is not None
            else settings.storage.max_image_dimension_px
        )
        self._allowed_formats = (
            allowed_formats
            if allowed_formats is not None
            else constants.SUPPORTED_IMAGE_PIL_FORMATS
        )

    def validate(self, path: Path) -> tuple[int, int, str]:
        """Validate the image at `path`, returning `(width, height, format)`.

        Raises `InvalidImageException` if the file can't be decoded at
        all (corrupted, truncated, or not actually an image despite its
        extension/declared type), `UnsupportedMediaTypeException` if it
        decodes to a format outside `constants.SUPPORTED_IMAGE_PIL_FORMATS`,
        or `ImageTooLargeException` if either dimension exceeds the
        configured maximum.
        """
        self._verify_integrity(path)
        width, height, image_format = self._decode(path)

        if image_format not in self._allowed_formats:
            raise UnsupportedMediaTypeException(
                f"Unsupported image format '{image_format}'. "
                f"Allowed formats: {', '.join(sorted(self._allowed_formats))}."
            )

        if width > self._max_dimension_px or height > self._max_dimension_px:
            raise ImageTooLargeException(
                f"Image dimensions {width}x{height} exceed the maximum of "
                f"{self._max_dimension_px}px per side."
            )

        return width, height, image_format

    def _verify_integrity(self, path: Path) -> None:
        """A cheap structural check: does this even look like a well-formed image file?

        `Image.verify()` does not decode pixel data, only the file
        structure/headers — fast, but it leaves the `Image` object unusable
        for anything else afterward (Pillow's own documented behavior),
        which is why `_decode` below reopens the file fresh rather than
        reusing this one.
        """
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            # Pillow raises different exception types across format
            # plugins and failure modes (OSError, SyntaxError, its own
            # UnidentifiedImageError, ...) for "this isn't decodable" —
            # catching broadly and converting to one domain exception
            # means callers never need to know Pillow's exception zoo.
            raise InvalidImageException(f"'{path.name}' failed an image integrity check.") from exc

    def _decode(self, path: Path) -> tuple[int, int, str]:
        """Fully decode the image (catching corruption `verify()` alone might miss)."""
        try:
            with Image.open(path) as image:
                image.load()
                width, height = image.size
                image_format = image.format
        except Exception as exc:
            raise InvalidImageException(
                f"'{path.name}' could not be decoded (corrupted image data)."
            ) from exc

        return width, height, image_format or "UNKNOWN"
