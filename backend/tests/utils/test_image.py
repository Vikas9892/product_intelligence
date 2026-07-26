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
