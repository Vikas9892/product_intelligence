"""Reusable validators for normalized product fields.

Called by `ProductService` *after* normalization — re-checking domain
invariants that either:

1. pydantic's schema-level validation on `ProductCreate` cannot express,
   because they only make sense against the *normalized* value. E.g. a
   name of `"   "` (three spaces) passes `Field(min_length=1)` before
   trimming (length 3), but is invalid once normalized to `""`.
2. should hold regardless of *which caller* constructs a domain `Product`
   — not just the one HTTP route. A future bulk-import path that builds
   `Product` objects directly (bypassing `ProductCreate`/FastAPI
   entirely) still needs these invariants enforced.

This is defense in depth, not redundant busywork: the domain layer
shouldn't blindly trust that every caller already validated correctly.
"""

from app.exceptions.errors import ValidationException


def validate_normalized_name(name: str) -> None:
    """Raise `ValidationException` if `name` is blank (e.g. was all whitespace)."""
    if not name:
        raise ValidationException("Product name must not be blank.")


def validate_price(price: float | None) -> None:
    """Raise `ValidationException` if `price` is present and negative."""
    if price is not None and price < 0:
        raise ValidationException("Product price must not be negative.")
