"""Unit tests for `VerificationReason`."""

import pytest
from pydantic import ValidationError

from app.models.verification_reason import VerificationReason


class TestVerificationReason:
    def test_constructs_with_code_and_message(self) -> None:
        reason = VerificationReason(code="same_brand", message="Same brand (Nike)")

        assert reason.code == "same_brand"
        assert reason.message == "Same brand (Nike)"

    def test_rejects_a_blank_code(self) -> None:
        with pytest.raises(ValidationError):
            VerificationReason(code="", message="something")

    def test_rejects_a_blank_message(self) -> None:
        with pytest.raises(ValidationError):
            VerificationReason(code="same_brand", message="")
