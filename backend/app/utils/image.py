"""Reusable image transformation helpers built on Pillow.

Pure functions over an already-open `PIL.Image.Image` — no file I/O, no
validation, no service state. `ImageProcessingService`
(`app/services/image_processing_service.py`) is the only thing that opens
files, calls these in sequence, and saves the result; keeping the
transformations themselves as free functions makes each one directly
unit-testable against an in-memory image, no disk or service required.
"""

from pathlib import Path
from typing import cast

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


#: A small, fixed set of reference colors — Phase 7's dominant-color
#: classification picks whichever of these is nearest (by squared
#: Euclidean RGB distance) to an image's actual dominant color, the same
#: "deterministic, not learned" spirit as `TextAttributeExtractionService`'s
#: keyword dictionaries.
_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "brown": (139, 69, 19),
}


def compute_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    """Return the single most representative RGB color in `image`.

    Downsamples to a small (50x50) thumbnail first — the dominant color
    of a product photo doesn't change based on resolution, and scanning
    every pixel of a full-size image for this would be needless work.
    """
    thumbnail = image.convert("RGB").resize((50, 50), Image.Resampling.LANCZOS)
    color_counts = thumbnail.getcolors(maxcolors=thumbnail.width * thumbnail.height)
    # `maxcolors` above covers every pixel in the thumbnail, so `getcolors`
    # can never actually return `None` here — this narrows its `Optional`
    # return type rather than handling a case that can't happen.
    assert color_counts is not None
    _, dominant_rgb = max(color_counts, key=lambda item: item[0])
    # `thumbnail` was converted to "RGB" above, so Pillow's own (mode-
    # dependent) `getcolors` stub is imprecise here — at runtime this is
    # always a 3-tuple, never the single-int form "L"/"1"-mode images use.
    return cast(tuple[int, int, int], dominant_rgb)


def classify_color_name(rgb: tuple[int, int, int]) -> str:
    """Return the closest named color (from a small, fixed palette) to `rgb`."""
    return min(
        _NAMED_COLORS,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(rgb, _NAMED_COLORS[name], strict=True)),
    )


def compute_brightness(image: Image.Image) -> float:
    """Return `image`'s mean pixel brightness, normalized to `[0, 1]`."""
    grayscale = image.convert("L")
    histogram = grayscale.histogram()
    total_pixels = grayscale.width * grayscale.height
    weighted_sum = sum(value * count for value, count in enumerate(histogram))
    return (weighted_sum / total_pixels) / 255 if total_pixels else 0.0


def classify_brightness(brightness: float) -> str:
    """Bucket a normalized `[0, 1]` brightness value into "dark"/"medium"/"bright"."""
    if brightness <= constants.BRIGHTNESS_DARK_MAX:
        return "dark"
    if brightness >= constants.BRIGHTNESS_BRIGHT_MIN:
        return "bright"
    return "medium"


def classify_orientation(width: int, height: int) -> str:
    """Bucket an image's dimensions into "portrait"/"landscape"/"square"."""
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def compute_aspect_ratio(width: int, height: int) -> float:
    """Return `width / height`."""
    return width / height


def classify_resolution(width: int, height: int) -> str:
    """Bucket an image's total pixel count into a "*_resolution" tag.

    Thresholds are fixed, codebase-decided constants
    (`constants.LOW_RESOLUTION_MAX_PIXELS`/`MEDIUM_RESOLUTION_MAX_PIXELS`),
    not something an operator would tune per-deployment.
    """
    total_pixels = width * height
    if total_pixels <= constants.LOW_RESOLUTION_MAX_PIXELS:
        return "low_resolution"
    if total_pixels <= constants.MEDIUM_RESOLUTION_MAX_PIXELS:
        return "medium_resolution"
    return "high_resolution"


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
