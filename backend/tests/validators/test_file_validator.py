"""Unit tests for `app.validators.file_validator`."""

import pytest

from app.exceptions.errors import UnsupportedMediaTypeException, ValidationException
from app.validators.file_validator import validate_filename_and_extension, validate_mime_type

_ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
_ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class TestValidateFilenameAndExtension:
    def test_accepts_an_allowed_extension(self) -> None:
        filename, extension = validate_filename_and_extension(
            "photo.jpg", allowed_extensions=_ALLOWED_EXTENSIONS
        )

        assert filename == "photo.jpg"
        assert extension == ".jpg"

    def test_lowercases_the_returned_extension(self) -> None:
        _, extension = validate_filename_and_extension(
            "photo.PNG", allowed_extensions=_ALLOWED_EXTENSIONS
        )

        assert extension == ".png"

    def test_rejects_none(self) -> None:
        with pytest.raises(ValidationException):
            validate_filename_and_extension(None, allowed_extensions=_ALLOWED_EXTENSIONS)

    def test_rejects_an_empty_string(self) -> None:
        with pytest.raises(ValidationException):
            validate_filename_and_extension("", allowed_extensions=_ALLOWED_EXTENSIONS)

    def test_rejects_a_disallowed_extension(self) -> None:
        with pytest.raises(UnsupportedMediaTypeException):
            validate_filename_and_extension("document.txt", allowed_extensions=_ALLOWED_EXTENSIONS)

    def test_rejects_a_filename_with_no_extension(self) -> None:
        with pytest.raises(UnsupportedMediaTypeException):
            validate_filename_and_extension("noextension", allowed_extensions=_ALLOWED_EXTENSIONS)


class TestValidateMimeType:
    def test_accepts_an_allowed_mime_type(self) -> None:
        result = validate_mime_type("image/jpeg", allowed_mime_types=_ALLOWED_MIME_TYPES)

        assert result == "image/jpeg"

    def test_rejects_none(self) -> None:
        with pytest.raises(UnsupportedMediaTypeException):
            validate_mime_type(None, allowed_mime_types=_ALLOWED_MIME_TYPES)

    def test_rejects_a_disallowed_mime_type(self) -> None:
        with pytest.raises(UnsupportedMediaTypeException):
            validate_mime_type("application/pdf", allowed_mime_types=_ALLOWED_MIME_TYPES)
