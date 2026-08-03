"""Deterministic product images, generated from nothing but the standard library.

Three requirements collide here, and this module is the resolution.

The images must be *legally safe*: no downloaded product photography, no
scraped catalogs. They are drawn from scratch by this file, so their
provenance is the source you are reading.

They must be *deterministic*: the same catalog entry must produce byte-identical
bytes on every machine and every run, or the "known relationships" the dataset
depends on stop being known. Nothing here uses randomness or the clock.

They must need *no dependencies*: the smoke suite is standard-library-only so
it can run anywhere against any deployment, which rules out Pillow. PNG turns
out to be simple enough to emit directly -- a header, one zlib-compressed
block of scanlines, and a terminator.

The shapes are crude on purpose. They are not pretending to be photographs;
they exist to give CLIP something visually consistent to embed, so that two
products the catalog calls similar really do produce similar vectors, and two
it calls unrelated really do not.
"""

from __future__ import annotations

import struct
import zlib

#: Bytes per pixel. Colour type 2 (truecolour, no alpha) -- alpha would add a
#: channel the models ignore and make the files larger for no benefit.
_CHANNELS = 3

RGB = tuple[int, int, int]


class Canvas:
    """A mutable RGB raster with the few primitives the catalog needs.

    Deliberately minimal: a background, rectangles and ellipses are enough to
    build recognisably distinct products, and every additional primitive would
    be code with no caller.
    """

    def __init__(self, width: int, height: int, background: RGB) -> None:
        self.width = width
        self.height = height
        # Flat bytearray rather than nested lists: it is the exact layout PNG
        # scanlines need, so encoding is a slice per row instead of a rebuild.
        self._pixels = bytearray(bytes(background) * (width * height))

    def _set(self, x: int, y: int, color: RGB) -> None:
        offset = (y * self.width + x) * _CHANNELS
        self._pixels[offset : offset + _CHANNELS] = bytes(color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        """Fill an axis-aligned rectangle, clipped to the canvas."""
        for y in range(max(0, y0), min(self.height, y1)):
            # Fill the row in one slice assignment rather than per pixel.
            start = (y * self.width + max(0, x0)) * _CHANNELS
            count = min(self.width, x1) - max(0, x0)
            if count > 0:
                self._pixels[start : start + count * _CHANNELS] = bytes(color) * count

    def ellipse(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        """Fill an axis-aligned ellipse inscribed in the given box."""
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = max((x1 - x0) / 2, 0.5), max((y1 - y0) / 2, 0.5)
        for y in range(max(0, int(y0)), min(self.height, int(y1) + 1)):
            dy = (y - cy) / ry
            for x in range(max(0, int(x0)), min(self.width, int(x1) + 1)):
                dx = (x - cx) / rx
                if dx * dx + dy * dy <= 1.0:
                    self._set(x, y, color)

    def to_png(self) -> bytes:
        """Encode as a PNG.

        Written out by hand rather than via a library. PNG is a signature plus
        a sequence of length-prefixed, CRC-checked chunks; only three are
        required for an uncompressed-colour image.
        """
        raw = bytearray()
        stride = self.width * _CHANNELS
        for y in range(self.height):
            # Filter type 0 (None) per scanline. The adaptive filters would
            # compress better, but these images are a few kilobytes either way
            # and unfiltered rows keep this readable.
            raw.append(0)
            raw += self._pixels[y * stride : (y + 1) * stride]

        header = struct.pack(
            ">IIBBBBB",
            self.width,
            self.height,
            8,  # bit depth
            2,  # colour type: truecolour
            0,  # compression: deflate
            0,  # filter method: adaptive
            0,  # interlace: none
        )
        return b"".join(
            [
                b"\x89PNG\r\n\x1a\n",
                _chunk(b"IHDR", header),
                # Fixed compression level, so output bytes are reproducible
                # rather than depending on a zlib default that could change.
                _chunk(b"IDAT", zlib.compress(bytes(raw), 6)),
                _chunk(b"IEND", b""),
            ]
        )


def _chunk(tag: bytes, data: bytes) -> bytes:
    """Length + type + data + CRC32 over (type + data)."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data))
    )


# -- Product renderers -----------------------------------------------------
# One function per product silhouette. Colour is a parameter so that "the same
# object in a different colour" and "a different object" are distinguishable
# to the vision model -- which is exactly the distinction the dataset's known
# relationships rest on.

SIZE = 320


def shoe(primary: RGB, sole: RGB, *, accent: RGB, variant: int = 0) -> bytes:
    """A side-on shoe silhouette.

    `variant` nudges the geometry by a few pixels. That is what builds the
    near-duplicate pair: two images that are visually the same object, without
    being the identical file -- so duplicate detection is exercised on genuine
    visual similarity rather than on a byte-for-byte match it could shortcut.
    """
    c = Canvas(SIZE, SIZE, (238, 240, 244))
    d = variant
    c.ellipse(48 + d, 150, 272 + d, 236, primary)  # upper
    c.rect(48 + d, 196, 272 + d, 236, primary)  # midsection
    c.rect(44 + d, 230, 276 + d, 252, sole)  # sole
    c.ellipse(150 + d, 132, 250 + d, 212, primary)  # heel collar
    c.rect(96 + d, 168, 108 + d, 214, accent)  # laces
    c.rect(124 + d, 164, 136 + d, 214, accent)
    c.rect(152 + d, 162, 164 + d, 214, accent)
    return c.to_png()


def mug(body: RGB, *, rim: RGB, variant: int = 0) -> bytes:
    """A mug seen from the side, with a handle."""
    c = Canvas(SIZE, SIZE, (246, 243, 236))
    d = variant
    c.ellipse(196, 120 + d, 288, 212 + d, body)  # handle (outer)
    c.ellipse(214, 138 + d, 270, 194 + d, (246, 243, 236))  # handle (hole)
    c.rect(84, 104 + d, 212, 244 + d, body)  # body
    c.ellipse(84, 88 + d, 212, 124 + d, rim)  # rim
    return c.to_png()


def backpack(body: RGB, *, strap: RGB, variant: int = 0) -> bytes:
    """A backpack: rounded body, lid panel, two straps."""
    c = Canvas(SIZE, SIZE, (236, 238, 240))
    d = variant
    c.ellipse(84, 76 + d, 236, 168 + d, body)  # lid
    c.rect(84, 120 + d, 236, 262 + d, body)  # body
    c.rect(104, 168 + d, 216, 208 + d, strap)  # front pocket band
    c.rect(96, 96 + d, 112, 150 + d, strap)  # straps
    c.rect(208, 96 + d, 224, 150 + d, strap)
    return c.to_png()


def lamp(shade: RGB, *, base: RGB) -> bytes:
    """A desk lamp -- deliberately unlike every other silhouette here."""
    c = Canvas(SIZE, SIZE, (240, 240, 236))
    c.ellipse(96, 56, 224, 148, shade)  # shade
    c.rect(154, 140, 166, 244, base)  # stem
    c.rect(112, 244, 208, 262, base)  # base
    return c.to_png()
