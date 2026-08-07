"""Reusable image transformation helpers built on Pillow.

Pure functions over an already-open `PIL.Image.Image` — no file I/O, no
validation, no service state. `ImageProcessingService`
(`app/services/image_processing_service.py`) is the only thing that opens
files, calls these in sequence, and saves the result; keeping the
transformations themselves as free functions makes each one directly
unit-testable against an in-memory image, no disk or service required.
"""

import colorsys
import math
from collections import Counter
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


#: Color-naming thresholds, in HLS. Saturation below this carries no usable
#: hue, so the color is achromatic (black/gray/white) regardless of channels.
_ACHROMATIC_MAX_SATURATION = 0.15
#: Lightness at or below this reads as black, whatever the hue.
#:
#: 0.20 is the conventional "blackish" boundary in color-naming systems, and
#: it is the right one for photographed products specifically: a black object
#: under studio lighting almost never measures near RGB 0. Charcoal readings
#: in the 40-55 range are normal, and the demo catalog's black items land at
#: (44, 46, 52) -- lightness 0.188. A boundary below that would name every
#: real black product "gray", which is the same class of error as naming a
#: blue one "gray".
_BLACK_MAX_LIGHTNESS = 0.20
#: Lightness at or above this reads as white when achromatic.
_WHITE_MIN_LIGHTNESS = 0.85
#: Hue (degrees) of each chromatic name. Derived from `_NAMED_COLORS` rather
#: than invented: these are the hues of those same RGB references.
_CHROMATIC_HUES: dict[str, float] = {
    "red": 0.0,
    "orange": 39.0,
    "yellow": 60.0,
    "green": 120.0,
    "blue": 240.0,
    "purple": 300.0,
    "pink": 350.0,
    "brown": 25.0,
}

#: Pixel-statistics tuning. Grouped here so the values that decide
#: "background vs subject" are visible in one place rather than buried inline.
#:
#: Analysis runs on a 50x50 thumbnail -- 2,500 pixels is ample for a dominant
#: color and keeps the per-pixel loops cheap.
_ANALYSIS_SIZE = 50
#: Fraction of the thumbnail treated as border when estimating the backdrop.
#: 0.10 of 50px is a 5px ring, enough to be robust to a subject touching one
#: edge without reaching into the middle of the frame.
_BORDER_FRACTION = 0.10
#: RGB Euclidean distance beyond which a pixel counts as subject, not backdrop.
#: Chosen from measured separation rather than tuned to one run: across the
#: demo catalog the *closest* genuine subject color sits ~180 from its own
#: backdrop (black shoe (44,46,52) against (238,240,244)), while resampling
#: and anti-aliasing around a subject edge stay within ~25. 60 sits clear of
#: the noise by more than 2x and clear of any real subject by 3x.
_BACKGROUND_DISTANCE = 60.0
#: If less of the frame than this survives background removal, treat the image
#: as having no separable subject and fall back to whole-frame statistics.
#: 2% of a 50x50 thumbnail is 50 pixels -- below that a "dominant color" is
#: being read off noise.
_MIN_SUBJECT_FRACTION = 0.02


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


def _thumbnail(image: Image.Image) -> Image.Image:
    """Downsample to a small RGB thumbnail for pixel statistics.

    The dominant color of a product photo does not change with resolution,
    and scanning every pixel of a full-size image for this would be needless
    work.
    """
    return image.convert("RGB").resize((_ANALYSIS_SIZE, _ANALYSIS_SIZE), Image.Resampling.LANCZOS)


def estimate_background_color(image: Image.Image) -> tuple[int, int, int]:
    """Estimate the backdrop color from the image's outer border.

    Product photography puts the subject in the middle against a plain
    backdrop, so the border ring is background with high reliability. The
    *median* of those pixels is used rather than the mean, so a subject that
    happens to touch one edge shifts the estimate far less than it would an
    average.
    """
    thumbnail = _thumbnail(image)
    pixels = thumbnail.load()
    assert pixels is not None
    size = thumbnail.width
    margin = max(1, round(size * _BORDER_FRACTION))

    border: list[tuple[int, int, int]] = []
    for y in range(size):
        in_horizontal_band = y < margin or y >= size - margin
        for x in range(size):
            if in_horizontal_band or x < margin or x >= size - margin:
                border.append(cast(tuple[int, int, int], pixels[x, y]))

    channels = tuple(sorted(channel[index] for channel in border) for index in range(3))
    middle = len(border) // 2
    return cast(tuple[int, int, int], tuple(channel[middle] for channel in channels))


def _subject_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    """Return the pixels that are not part of the backdrop.

    Everything within `_BACKGROUND_DISTANCE` of the estimated background color
    is dropped. What remains is the subject -- which is what every caller
    actually wants to describe.

    Returns an empty list when almost nothing survives; callers fall back to
    whole-frame statistics, because an image that is background nearly
    everywhere genuinely has no separable subject to describe.
    """
    background = estimate_background_color(image)
    thumbnail = _thumbnail(image)
    pixels = thumbnail.load()
    assert pixels is not None

    subject = [
        rgb
        for y in range(thumbnail.height)
        for x in range(thumbnail.width)
        if _distance(rgb := cast(tuple[int, int, int], pixels[x, y]), background)
        > _BACKGROUND_DISTANCE
    ]
    total = thumbnail.width * thumbnail.height
    return subject if len(subject) >= total * _MIN_SUBJECT_FRACTION else []


def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    """Euclidean distance between two RGB triples."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def compute_dominant_color(image: Image.Image) -> tuple[int, int, int]:
    """Return the dominant RGB color of the image's *subject*.

    Background pixels are excluded first. Without that, this returned the
    backdrop for essentially every product photo: measured against the demo
    catalog, a black shoe, a red mug, a blue shoe and a black backpack all
    reported (238, 240, 244) -- the studio-white background -- and were
    classified "white". Color was therefore never a property of the product.

    A white element *on* a white background is genuinely indistinguishable
    without real segmentation, so it is treated as background here. That is a
    known and accepted limit of a threshold-based approach.
    """
    subject = _subject_pixels(image)
    if not subject:
        # No separable subject: fall back to whole-frame, which is the honest
        # answer for a solid or near-solid image.
        thumbnail = _thumbnail(image)
        pixels = thumbnail.load()
        assert pixels is not None
        subject = [
            cast(tuple[int, int, int], pixels[x, y])
            for y in range(thumbnail.height)
            for x in range(thumbnail.width)
        ]

    counts = Counter(subject)
    return counts.most_common(1)[0][0]


def classify_color_name(rgb: tuple[int, int, int]) -> str:
    """Return the nearest named color, judging hue separately from lightness.

    Nearest-neighbour in raw RGB looks reasonable and is not: the achromatic
    entries (black, gray, white) sit in the middle of the RGB cube and so
    attract saturated colors that are nowhere near them. Measured on the demo
    catalog, a genuine blue (36, 82, 168) came out "gray" -- it is 12,180 from
    gray but 15,589 from blue -- and a dark blue (24, 58, 122) came out
    "purple". Naming a blue product "gray" is as wrong to a user as the
    background bias this function sits downstream of.

    So the decision is split the way human color naming works:

    * Low saturation means achromatic. Only black/gray/white are candidates,
      chosen by lightness -- hue is meaningless noise at that saturation.
    * Otherwise the color is chromatic, and hue decides. Distance is measured
      as circular hue difference, so red at 0 and red at 359 are adjacent.
      Very dark chromatic pixels still resolve to black, because a hue is not
      perceptible below that lightness.

    Deterministic and dependency-free, in the same spirit as the rest of the
    catalog-intelligence heuristics.
    """
    red, green, blue = (channel / 255 for channel in rgb)
    hue_turns, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    if saturation < _ACHROMATIC_MAX_SATURATION:
        if lightness <= _BLACK_MAX_LIGHTNESS:
            return "black"
        return "white" if lightness >= _WHITE_MIN_LIGHTNESS else "gray"

    # Chromatic, but too dark for any hue to read as that color.
    if lightness <= _BLACK_MAX_LIGHTNESS:
        return "black"

    hue = hue_turns * 360
    return min(_CHROMATIC_HUES, key=lambda name: _hue_distance(hue, _CHROMATIC_HUES[name]))


def _hue_distance(left: float, right: float) -> float:
    """Shortest distance between two hues on the 0-360 degree circle."""
    delta = abs(left - right) % 360
    return min(delta, 360 - delta)


def compute_brightness(image: Image.Image) -> float:
    """Return the mean brightness of the image's *subject*, normalized to `[0, 1]`.

    Subject-scoped for the same reason as `compute_dominant_color`: averaged
    over the whole frame, a dark product on a studio-white background reads as
    "bright", which describes the backdrop rather than the product. Every item
    in the demo catalog measured 0.75-0.85 and was tagged "bright", including
    two black ones.

    Falls back to the whole frame when no subject separates out.
    """
    subject = _subject_pixels(image)
    if subject:
        # Rec. 601 luma, matching Pillow's own "L" conversion.
        total = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in subject)
        return total / len(subject) / 255

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
