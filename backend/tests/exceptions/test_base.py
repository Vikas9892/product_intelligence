"""Unit tests for the `AppException` base class."""

from app.exceptions.base import AppException


class TestAppException:
    def test_uses_class_level_defaults_when_no_message_is_given(self) -> None:
        exc = AppException()

        assert exc.status_code == 500
        assert exc.code == "internal_error"
        assert exc.message == "An unexpected error occurred."
        assert exc.details is None

    def test_a_custom_message_overrides_the_default(self) -> None:
        exc = AppException("something specific went wrong")

        assert exc.message == "something specific went wrong"
        assert str(exc) == "something specific went wrong"

    def test_details_are_stored_as_given(self) -> None:
        exc = AppException(details={"field": "email"})

        assert exc.details == {"field": "email"}

    def test_subclasses_can_override_status_code_and_code(self) -> None:
        class TeapotException(AppException):
            status_code = 418
            code = "teapot"
            message = "I'm a teapot."

        exc = TeapotException()

        assert exc.status_code == 418
        assert exc.code == "teapot"
        assert exc.message == "I'm a teapot."
