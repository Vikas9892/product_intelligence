"""Unit tests for `app.utils.image`, against in-memory Pillow images (no disk I/O)."""

from PIL import Image

from app.utils.image import (
    apply_orientation,
    classify_brightness,
    classify_color_name,
    classify_orientation,
    classify_resolution,
    compute_aspect_ratio,
    compute_brightness,
    compute_dominant_color,
    estimate_background_color,
    generate_processed_filename,
    normalize_color_mode,
    resize_preserving_aspect_ratio,
)

_EXIF_ORIENTATION_TAG = 0x0112


def _image_with_exif_orientation(orientation: int, *, size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, (255, 0, 0))
    exif = image.getexif()
    exif[_EXIF_ORIENTATION_TAG] = orientation
    image.info["exif"] = exif.tobytes()
    return image


class TestApplyOrientation:
    def test_rotates_an_image_with_a_90_degree_orientation_tag(self) -> None:
        image = _image_with_exif_orientation(6, size=(100, 50))

        transposed = apply_orientation(image)

        assert transposed.size == (50, 100)

    def test_leaves_a_normally_oriented_image_unchanged(self) -> None:
        image = _image_with_exif_orientation(1, size=(100, 50))

        result = apply_orientation(image)

        assert result.size == (100, 50)

    def test_leaves_an_image_with_no_exif_data_unchanged(self) -> None:
        image = Image.new("RGB", (100, 50), (0, 255, 0))

        result = apply_orientation(image)

        assert result.size == (100, 50)


class TestNormalizeColorMode:
    def test_returns_an_already_rgb_image_unchanged(self) -> None:
        image = Image.new("RGB", (10, 10), (1, 2, 3))

        result = normalize_color_mode(image)

        assert result is image

    def test_flattens_rgba_transparency_onto_white(self) -> None:
        image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))  # fully transparent black

        result = normalize_color_mode(image)

        assert result.mode == "RGB"
        assert result.getpixel((0, 0)) == (255, 255, 255)

    def test_preserves_opaque_rgba_pixel_color(self) -> None:
        image = Image.new("RGBA", (2, 2), (10, 20, 30, 255))  # fully opaque

        result = normalize_color_mode(image)

        assert result.mode == "RGB"
        assert result.getpixel((0, 0)) == (10, 20, 30)

    def test_converts_grayscale_to_rgb(self) -> None:
        image = Image.new("L", (5, 5), 128)

        result = normalize_color_mode(image)

        assert result.mode == "RGB"

    def test_converts_palette_mode_without_transparency_to_rgb(self) -> None:
        image = Image.new("P", (5, 5))

        result = normalize_color_mode(image)

        assert result.mode == "RGB"


class TestResizePreservingAspectRatio:
    def test_downscales_a_larger_image_preserving_aspect_ratio(self) -> None:
        image = Image.new("RGB", (200, 100), (0, 0, 0))

        resized = resize_preserving_aspect_ratio(image, max_dimension=50)

        assert resized.size == (50, 25)

    def test_leaves_a_smaller_image_unchanged(self) -> None:
        image = Image.new("RGB", (40, 20), (0, 0, 0))

        result = resize_preserving_aspect_ratio(image, max_dimension=100)

        assert result is image

    def test_leaves_an_image_exactly_at_the_limit_unchanged(self) -> None:
        image = Image.new("RGB", (100, 100), (0, 0, 0))

        result = resize_preserving_aspect_ratio(image, max_dimension=100)

        assert result is image

    def test_handles_a_tiny_image_without_producing_a_zero_sized_result(self) -> None:
        image = Image.new("RGB", (1, 1), (0, 0, 0))

        result = resize_preserving_aspect_ratio(image, max_dimension=1000)

        assert result.size == (1, 1)


class TestGenerateProcessedFilename:
    def test_replaces_the_extension_with_the_standardized_one(self) -> None:
        assert generate_processed_filename("abc123.png") == "abc123.jpg"
        assert generate_processed_filename("abc123.webp") == "abc123.jpg"

    def test_is_a_no_op_extension_wise_for_an_already_jpg_name(self) -> None:
        assert generate_processed_filename("abc123.jpg") == "abc123.jpg"


class TestComputeDominantColor:
    def test_returns_the_only_color_in_a_solid_image(self) -> None:
        image = Image.new("RGB", (40, 40), (200, 30, 30))

        assert compute_dominant_color(image) == (200, 30, 30)

    def test_returns_the_majority_color_when_mixed(self) -> None:
        image = Image.new("RGB", (40, 40), (0, 0, 255))
        for x in range(2):  # a small minority patch of a different color
            for y in range(2):
                image.putpixel((x, y), (255, 0, 0))

        assert compute_dominant_color(image) == (0, 0, 255)

    def test_handles_a_grayscale_image(self) -> None:
        image = Image.new("L", (40, 40), 128)

        color = compute_dominant_color(image)

        assert color == (128, 128, 128)


class TestClassifyColorName:
    def test_classifies_pure_red(self) -> None:
        assert classify_color_name((255, 0, 0)) == "red"

    def test_classifies_pure_black(self) -> None:
        assert classify_color_name((0, 0, 0)) == "black"

    def test_classifies_pure_white(self) -> None:
        assert classify_color_name((255, 255, 255)) == "white"

    def test_classifies_a_near_match(self) -> None:
        assert classify_color_name((250, 5, 5)) == "red"


class TestComputeBrightness:
    def test_black_image_has_zero_brightness(self) -> None:
        image = Image.new("RGB", (20, 20), (0, 0, 0))

        assert compute_brightness(image) == 0.0

    def test_white_image_has_full_brightness(self) -> None:
        image = Image.new("RGB", (20, 20), (255, 255, 255))

        assert compute_brightness(image) == 1.0

    def test_mid_gray_image_has_roughly_half_brightness(self) -> None:
        image = Image.new("RGB", (20, 20), (128, 128, 128))

        assert 0.4 < compute_brightness(image) < 0.6


class TestClassifyBrightness:
    def test_classifies_dark(self) -> None:
        assert classify_brightness(0.1) == "dark"

    def test_classifies_bright(self) -> None:
        assert classify_brightness(0.9) == "bright"

    def test_classifies_medium(self) -> None:
        assert classify_brightness(0.5) == "medium"


class TestClassifyOrientation:
    def test_classifies_portrait(self) -> None:
        assert classify_orientation(100, 200) == "portrait"

    def test_classifies_landscape(self) -> None:
        assert classify_orientation(200, 100) == "landscape"

    def test_classifies_square(self) -> None:
        assert classify_orientation(150, 150) == "square"


class TestComputeAspectRatio:
    def test_computes_a_wide_ratio(self) -> None:
        assert compute_aspect_ratio(200, 100) == 2.0

    def test_computes_a_tall_ratio(self) -> None:
        assert compute_aspect_ratio(100, 200) == 0.5


class TestClassifyResolution:
    def test_classifies_low_resolution(self) -> None:
        assert classify_resolution(100, 100) == "low_resolution"

    def test_classifies_medium_resolution(self) -> None:
        assert classify_resolution(800, 800) == "medium_resolution"

    def test_classifies_high_resolution(self) -> None:
        assert classify_resolution(2000, 2000) == "high_resolution"


def _product_photo(subject: tuple[int, int, int], background: tuple[int, int, int]) -> Image.Image:
    """A product photo: a subject centred on a plain backdrop.

    The subject deliberately occupies a *minority* of the frame, as in real
    product photography -- which is exactly the condition under which
    whole-frame statistics report the backdrop instead of the product.
    """
    image = Image.new("RGB", (200, 200), background)
    for y in range(70, 130):
        for x in range(60, 140):
            image.putpixel((x, y), subject)
    return image


class TestSubjectIsolation:
    """Regression tests for attributes describing the backdrop, not the product.

    Measured before the fix, every item in the demo catalog -- a black shoe, a
    red mug, a blue shoe, a black backpack -- reported dominant colour
    (238, 240, 244) and was tagged "white" and "bright". Colour and brightness
    were properties of the studio background, never of the product.
    """

    def test_a_black_product_on_a_white_background_is_black(self) -> None:
        photo = _product_photo(subject=(44, 46, 52), background=(238, 240, 244))

        assert classify_color_name(compute_dominant_color(photo)) == "black"

    def test_a_black_product_on_a_white_background_is_not_bright(self) -> None:
        photo = _product_photo(subject=(44, 46, 52), background=(238, 240, 244))

        assert classify_brightness(compute_brightness(photo)) == "dark"

    def test_a_red_product_on_a_cream_background_is_red(self) -> None:
        photo = _product_photo(subject=(176, 58, 46), background=(246, 243, 236))

        assert classify_color_name(compute_dominant_color(photo)) == "red"

    def test_the_backdrop_is_estimated_from_the_border(self) -> None:
        photo = _product_photo(subject=(44, 46, 52), background=(238, 240, 244))

        assert estimate_background_color(photo) == (238, 240, 244)

    def test_a_solid_image_falls_back_to_whole_frame_statistics(self) -> None:
        """No separable subject is an honest answer, not an error."""
        solid = Image.new("RGB", (100, 100), (200, 30, 30))

        assert compute_dominant_color(solid) == (200, 30, 30)

    def test_a_subject_touching_one_edge_still_resolves(self) -> None:
        """The median border estimate tolerates a subject bleeding off-frame."""
        image = Image.new("RGB", (200, 200), (240, 240, 240))
        for y in range(0, 120):
            for x in range(0, 90):
                image.putpixel((x, y), (20, 90, 200))

        assert classify_color_name(compute_dominant_color(image)) == "blue"


class TestChromaticColorNaming:
    """Naming must judge hue separately from lightness.

    Nearest-neighbour in raw RGB put a genuine blue (36, 82, 168) closer to
    gray (12,180) than to blue (15,589), so real product colours were named
    "gray" and "purple".
    """

    def test_a_mid_blue_is_blue_not_gray(self) -> None:
        assert classify_color_name((36, 82, 168)) == "blue"

    def test_a_dark_blue_is_blue_not_purple(self) -> None:
        assert classify_color_name((24, 58, 122)) == "blue"

    def test_a_brick_red_is_red_not_brown(self) -> None:
        assert classify_color_name((176, 58, 46)) == "red"

    def test_desaturated_mid_tones_are_still_gray(self) -> None:
        assert classify_color_name((128, 128, 128)) == "gray"

    def test_a_very_dark_saturated_color_reads_as_black(self) -> None:
        """Hue is not perceptible at that lightness."""
        assert classify_color_name((10, 4, 20)) == "black"
