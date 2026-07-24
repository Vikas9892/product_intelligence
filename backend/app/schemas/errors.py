"""The single JSON error envelope every failure response uses.

`app/exceptions/handlers.py` builds one of these for every error path —
an `AppException`, FastAPI's own request-validation failures, a plain
`HTTPException`, and any unhandled exception — so an API consumer only
ever has to parse one shape, regardless of what went wrong.
"""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """The `error` object inside an `ErrorResponse`."""

    #: Stable, machine-readable identifier (e.g. "resource_not_found") for
    #: clients to branch on. Distinct from the HTTP status code — see
    #: `app/exceptions/base.py` for why.
    code: str
    #: Human-readable message. Safe to display to an end user or log —
    #: never the raw internals of an unexpected exception (see
    #: `_handle_unexpected_exception` in handlers.py).
    message: str
    #: Optional machine-readable extra context, e.g. per-field validation
    #: errors. `None` when there's nothing structured to add.
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Top-level error response body."""

    success: Literal[False] = False
    error: ErrorDetail
