"""Reusable image transformation helpers built on Pillow.

Pure functions over an already-open `PIL.Image.Image` — no file I/O, no
validation, no service state. `ImageProcessingService`
(`app/services/image_processing_service.py`) is the only thing that opens
files, calls these in sequence, and saves the result; keeping the
transformations themselves as free functions makes each one directly
unit-testable against an in-memory image, no disk or service required.
"""

from pathlib import Path

from PIL import Image, ImageOps

from app.core import constants


def apply_orientation(image: Image.Image) -> Image.Image:
    """Rotate/flip `image` per its EXIF Orientation tag, then strip that tag.

    Cameras and phones often store images "sideways" with an EXIF tag
    saying how a viewer should rotate them for display, rather than
    rotating the pixel data itself. Downstream AI models have no concept
    of EXIF — they only see the pixel grid — so orientation must be baked
    into the pixels themselves before any further processing.
    `ImageOps.exif_transpose` handles all eight possible EXIF orientation
    values (including flips) correctly; if there's no orientation tag (or
    it's already `1`, meaning "normal"), it returns an equivalent copy of
    `image` unchanged.
    """
    return ImageOps.exif_transpose(image) or image


def normalize_color_mode(image: Image.Image) -> Image.Image:
    """Convert `image` to plain RGB, flattening any transparency onto white.

    AI models like CLIP/DINOv2 expect a consistent 3-channel RGB input —
    real-world uploads arrive in many different Pillow modes (`RGBA` with
    an alpha channel, palette-based `P` images that may themselves carry
    transparency, grayscale `L`, `CMYK` from some scanners/print
    workflows, etc.). A transparent pixel has no defined color by itself,
    so it's composited onto an opaque white background before dropping
    the alpha channel — silently discarding transparency (e.g. via a bare
    `.convert("RGB")`) would instead blend it against whatever arbitrary
    default the decoder chooses, which is inconsistent across formats.
    """
    if image.mode == "RGB":
        return image

    if _has_transparency(image):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background

    return image.convert("RGB")


def _has_transparency(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def resize_preserving_aspect_ratio(image: Image.Image, *, max_dimension: int) -> Image.Image:
    """Downscale `image` so neither side exceeds `max_dimension`, preserving aspect ratio.

    A no-op (returns `image` unchanged) if it already fits — this never
    *upscales* a smaller image, which would fabricate detail that was
    never there. `Image.Resampling.LANCZOS` is used for downscaling: it
    produces noticeably sharper results than the faster nearest-neighbor
    or bilinear filters, at a cost that's irrelevant for a one-time
    processing step (as opposed to, say, real-time video resizing).
    """
    width, height = image.size
    if width <= max_dimension and height <= max_dimension:
        return image

    scale = min(max_dimension / width, max_dimension / height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def generate_processed_filename(stored_filename: str) -> str:
    """Derive the processed output's filename from an already-stored file's name.

    Every processed image is re-encoded to one standardized format
    (`constants.PROCESSED_IMAGE_FORMAT`) regardless of its original
    one — see `ImageProcessingService` for why — so the output extension
    is always `constants.PROCESSED_IMAGE_EXTENSION`, not whatever the
    input had. `stored_filename` is already a server-generated identifier
    (never client-supplied — see `UploadService`), so reusing its stem
    here introduces no new path-traversal risk.
    """
    return f"{Path(stored_filename).stem}{constants.PROCESSED_IMAGE_EXTENSION}"
