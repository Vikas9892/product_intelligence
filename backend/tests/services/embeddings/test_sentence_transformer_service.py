"""Unit tests for `SentenceTransformerEmbeddingService`.

Logic tests (batching, normalization, error wrapping) inject a fake model
via `TextModelManager` so they're fast and don't depend on real model
weights — the same strategy `test_clip_service.py` uses for
`CLIPEmbeddingService`. `TestRealSentenceTransformerEmbedding` proves the
actual `sentence-transformers`/`torch` wiring works end-to-end against a
real, small, widely-cached checkpoint.
"""

from typing import cast

import numpy as np
import pytest
from sentence_transformers import SentenceTransformer

from app.exceptions.errors import TextEmbeddingException
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.services.embeddings.sentence_transformer_service import (
    SentenceTransformerEmbeddingService,
)
from app.services.embeddings.text_model_manager import TextModelManager
from app.services.model_registry import ModelRegistry

_REAL_TINY_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class _FakeSentenceTransformerModel:
    """Returns a deterministic, non-uniform array shaped (batch_size, dimension)."""

    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension
        self.encode_batch_sizes: list[int] = []

    def to(self, device: object) -> "_FakeSentenceTransformerModel":
        return self

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> np.ndarray:
        self.encode_batch_sizes.append(len(texts))
        return np.arange(1, len(texts) * self.dimension + 1, dtype=np.float32).reshape(
            len(texts), self.dimension
        )


class _RaisingSentenceTransformerModel:
    def to(self, device: object) -> "_RaisingSentenceTransformerModel":
        return self

    def encode(self, texts: list[str], **kwargs: object) -> np.ndarray:
        raise RuntimeError("boom")


def _fake_model_manager(
    *, model: _FakeSentenceTransformerModel | _RaisingSentenceTransformerModel | None = None
) -> TextModelManager:
    fake_model = model if model is not None else _FakeSentenceTransformerModel()
    return TextModelManager(
        device="cpu",
        model_loader=lambda name: cast(SentenceTransformer, fake_model),
    )


class TestEmbedText:
    async def test_returns_a_single_vector(self) -> None:
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model", dimension=4, model_manager=_fake_model_manager()
        )

        vector = await service.embed_text("a red widget")

        assert len(vector) == 4

    async def test_raises_text_embedding_exception_on_inference_failure(self) -> None:
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model",
            dimension=4,
            model_manager=_fake_model_manager(model=_RaisingSentenceTransformerModel()),
        )

        with pytest.raises(TextEmbeddingException):
            await service.embed_text("a red widget")


class TestEmbedBatch:
    async def test_returns_one_vector_per_input_in_order(self) -> None:
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model", dimension=4, model_manager=_fake_model_manager()
        )

        vectors = await service.embed_batch(["a", "b", "c"])

        assert len(vectors) == 3
        assert all(len(vector) == 4 for vector in vectors)

    async def test_returns_an_empty_list_for_no_input(self) -> None:
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model", model_manager=_fake_model_manager()
        )

        assert await service.embed_batch([]) == []

    async def test_chunks_requests_larger_than_the_configured_batch_size(self) -> None:
        fake_model = _FakeSentenceTransformerModel()
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model",
            batch_size=2,
            model_manager=_fake_model_manager(model=fake_model),
        )

        vectors = await service.embed_batch(["a", "b", "c", "d", "e"])

        assert len(vectors) == 5
        assert fake_model.encode_batch_sizes == [2, 2, 1]

    async def test_raises_text_embedding_exception_on_inference_failure(self) -> None:
        service = SentenceTransformerEmbeddingService(
            model_name="fake-model",
            model_manager=_fake_model_manager(model=_RaisingSentenceTransformerModel()),
        )

        with pytest.raises(TextEmbeddingException):
            await service.embed_batch(["a", "b"])


class TestModelNameAndDimension:
    def test_model_name_defaults_to_settings(self) -> None:
        service = SentenceTransformerEmbeddingService(model_manager=_fake_model_manager())

        assert service.model_name == "BAAI/bge-small-en-v1.5"

    def test_dimension_defaults_without_loading_a_model(self) -> None:
        manager = _fake_model_manager()
        service = SentenceTransformerEmbeddingService(model_manager=manager)

        assert service.dimension == 384
        assert manager.is_loaded(service.model_name) is False


class TestModelRegistryResolution:
    def test_uses_the_explicit_model_name_when_given_ignoring_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-model",
                version="1.0.0",
                model_type=ModelType.TEXT_EMBEDDING,
                dimension=384,
                status=ModelStatus.ACTIVE,
            )
        )

        service = SentenceTransformerEmbeddingService(
            model_name="explicit-model", model_registry=registry
        )

        assert service.model_name == "explicit-model"

    def test_resolves_the_active_text_embedding_model_from_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-text-model",
                version="1.0.0",
                model_type=ModelType.TEXT_EMBEDDING,
                dimension=384,
                status=ModelStatus.ACTIVE,
            )
        )

        service = SentenceTransformerEmbeddingService(model_registry=registry)

        assert service.model_name == "registry-text-model"


class TestRealSentenceTransformerEmbedding:
    async def test_generates_a_real_normalized_embedding(self) -> None:
        model_manager = TextModelManager(device="cpu")
        service = SentenceTransformerEmbeddingService(
            model_name=_REAL_TINY_MODEL_NAME, dimension=384, model_manager=model_manager
        )

        vector = await service.embed_text("a red running shoe")

        assert len(vector) == 384
        norm = sum(component**2 for component in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-4)

    async def test_generates_real_batch_embeddings(self) -> None:
        model_manager = TextModelManager(device="cpu")
        service = SentenceTransformerEmbeddingService(
            model_name=_REAL_TINY_MODEL_NAME, dimension=384, model_manager=model_manager
        )

        vectors = await service.embed_batch(["a red running shoe", "a blue cotton shirt"])

        assert len(vectors) == 2
        assert len(vectors[0]) == len(vectors[1]) == 384
