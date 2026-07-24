"""Unit tests for the concrete domain-agnostic exception types."""

from app.exceptions.base import AppException
from app.exceptions.errors import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)


class TestValidationException:
    def test_defaults(self) -> None:
        exc = ValidationException()

        assert isinstance(exc, AppException)
        assert exc.status_code == 422
        assert exc.code == "validation_error"


class TestResourceNotFoundException:
    def test_defaults(self) -> None:
        exc = ResourceNotFoundException()

        assert exc.status_code == 404
        assert exc.code == "resource_not_found"
        assert exc.details is None

    def test_custom_message_and_resource_name(self) -> None:
        exc = ResourceNotFoundException("product 42 not found", resource="product")

        assert exc.message == "product 42 not found"
        assert exc.details == {"resource": "product"}


class TestConflictException:
    def test_defaults(self) -> None:
        exc = ConflictException()

        assert exc.status_code == 409
        assert exc.code == "conflict"
