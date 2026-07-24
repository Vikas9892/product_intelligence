"""Unit tests for the `BaseEmbeddingService` interface."""

from pathlib import Path

import pytest

from app.services.embeddings.base import BaseEmbeddingService


class TestBaseEmbeddingService:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseEmbeddingService()  # type: ignore[abstract]

    async def test_a_conforming_subclass_can_be_instantiated_and_used(self) -> None:
        class _FakeEmbeddingService(BaseEmbeddingService):
            @property
            def model_name(self) -> str:
                return "fake-model"

            async def generate_embedding(self, image_path: Path) -> list[float]:
                return [0.1, 0.2]

            async def generate_embeddings(self, image_paths: list[Path]) -> list[list[float]]:
                return [[0.1, 0.2] for _ in image_paths]

        service = _FakeEmbeddingService()

        assert service.model_name == "fake-model"
        assert await service.generate_embedding(Path("a.jpg")) == [0.1, 0.2]
        assert await service.generate_embeddings([Path("a.jpg"), Path("b.jpg")]) == [
            [0.1, 0.2],
            [0.1, 0.2],
        ]

    def test_a_subclass_missing_a_method_cannot_be_instantiated(self) -> None:
        class _IncompleteEmbeddingService(BaseEmbeddingService):
            @property
            def model_name(self) -> str:
                return "fake-model"

            async def generate_embedding(self, image_path: Path) -> list[float]:
                return []

        with pytest.raises(TypeError):
            _IncompleteEmbeddingService()  # type: ignore[abstract]
