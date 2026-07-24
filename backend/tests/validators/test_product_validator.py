"""Unit tests for `app.validators.product_validator`."""

import pytest

from app.exceptions.errors import ValidationException
from app.validators.product_validator import validate_normalized_name, validate_price


class TestValidateNormalizedName:
    def test_accepts_a_non_blank_name(self) -> None:
        validate_normalized_name("Widget")  # must not raise

    def test_rejects_an_empty_string(self) -> None:
        with pytest.raises(ValidationException):
            validate_normalized_name("")


class TestValidatePrice:
    def test_accepts_none(self) -> None:
        validate_price(None)  # must not raise

    def test_accepts_zero(self) -> None:
        validate_price(0.0)  # must not raise

    def test_accepts_a_positive_price(self) -> None:
        validate_price(19.99)  # must not raise

    def test_rejects_a_negative_price(self) -> None:
        with pytest.raises(ValidationException):
            validate_price(-0.01)
