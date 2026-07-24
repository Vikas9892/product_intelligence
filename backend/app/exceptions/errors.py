"""Concrete, domain-agnostic application exceptions.

Each subclass fixes one (`status_code`, `code`) pair for a category of
failure that recurs across any resource-oriented API. They're intentionally
generic ("a resource wasn't found", not "a product wasn't found") — a
later milestone's product/search code raises `ResourceNotFoundException`
the same way user/auth code eventually would, instead of every domain
reinventing its own not-found exception.
"""

from typing import Any

from app.exceptions.base import AppException


class ValidationException(AppException):
    """A request was semantically invalid in a way schema validation alone can't express.

    FastAPI already returns 422 for requests that fail Pydantic *schema*
    validation (missing/mistyped fields) — that path is handled separately
    in `handlers.py` via `RequestValidationError`. Raise this instead for
    validation that requires business logic to detect (e.g. "end_date must
    be after start_date"), which schema validation alone can't express.
    """

    status_code = 422
    code = "validation_error"
    message = "The request was invalid."


class ResourceNotFoundException(AppException):
    """The requested resource does not exist."""

    status_code = 404
    code = "resource_not_found"
    message = "The requested resource was not found."

    def __init__(self, message: str | None = None, *, resource: str | None = None) -> None:
        details: dict[str, Any] | None = {"resource": resource} if resource else None
        super().__init__(message, details=details)


class ConflictException(AppException):
    """The request conflicts with the current state of the resource.

    E.g. a uniqueness constraint violation, or a stale/optimistic-locking
    conflict on update.
    """

    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state of the resource."
