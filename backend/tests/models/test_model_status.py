"""Unit tests for `ModelStatus`."""

from app.models.model_status import ModelStatus


class TestModelStatus:
    def test_has_the_four_lifecycle_states(self) -> None:
        assert {status.value for status in ModelStatus} == {
            "active",
            "inactive",
            "deprecated",
            "experimental",
        }
