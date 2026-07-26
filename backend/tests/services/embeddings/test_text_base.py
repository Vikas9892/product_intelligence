"""Unit tests for the `BaseTextEmbeddingService` interface."""

import pytest

from app.services.embeddings.text_base import BaseTextEmbeddingService


class TestBaseTextEmbeddingService:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseTextEmbeddingService()  # type: ignore[abstract]

    async def test_a_conforming_subclass_can_be_instantiated_and_used(self) -> None:
        class _FakeTextEmbeddingService(BaseTextEmbeddingService):
            @property
            def model_name(self) -> str:
                return "fake-text-model"

            @property
            def dimension(self) -> int:
                return 2

            async def embed_text(self, text: str) -> list[float]:
                return [0.1, 0.2]

            async def embed_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.1, 0.2] for _ in texts]

        service = _FakeTextEmbeddingService()

        assert service.model_name == "fake-text-model"
        assert service.dimension == 2
        assert await service.embed_text("hello") == [0.1, 0.2]
        assert await service.embed_batch(["hello", "world"]) == [[0.1, 0.2], [0.1, 0.2]]

    def test_a_subclass_missing_a_method_cannot_be_instantiated(self) -> None:
        class _IncompleteTextEmbeddingService(BaseTextEmbeddingService):
            @property
            def model_name(self) -> str:
                return "fake-text-model"

            @property
            def dimension(self) -> int:
                return 2

            async def embed_text(self, text: str) -> list[float]:
                return []

        with pytest.raises(TypeError):
            _IncompleteTextEmbeddingService()  # type: ignore[abstract]
