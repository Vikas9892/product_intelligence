"""Unit tests for `ModelType`."""

from app.models.model_type import ModelType


class TestModelType:
    def test_has_the_three_model_types(self) -> None:
        assert {model_type.value for model_type in ModelType} == {
            "image_embedding",
            "text_embedding",
            "reranker",
        }
