"""Base class for every application-raised exception.

Business/domain code should raise a subclass of `AppException` (see
`errors.py`) rather than `fastapi.HTTPException` directly. `HTTPException`
only carries an HTTP status code and a free-text `detail` string — it has
no place for a stable, machine-readable error identifier, so every call
site that raises one has to invent its own `detail` wording, and clients
can only distinguish error cases by string-matching that wording (which
changes) or by status code alone (which is often ambiguous — many
different failures are all legitimately 400 or 404). `AppException` fixes
both problems: `status_code` is the *transport* concern (what HTTP status
to send), `code` is the *API contract* concern (a stable string like
`"resource_not_found"` a client can safely switch on across releases,
independent of the human-readable `message` wording).

`app/exceptions/handlers.py` catches this base class once and converts any
subclass into the same JSON envelope — new exception types (see
`errors.py`) never require touching the handler.
"""

from typing import Any


class AppException(Exception):
    """Base class for all domain-raised exceptions.

    Subclasses override the `status_code`, `code`, and `message` class
    attributes to declare their defaults; `message` (and optionally
    `details`) can also be overridden per-instance when raised, for a
    message specific to what actually happened (e.g. *which* resource
    was not found).
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, details: Any | None = None) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)
