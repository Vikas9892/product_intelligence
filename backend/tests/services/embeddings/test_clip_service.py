"""Unit tests for `CLIPEmbeddingService`.

Logic tests (batching, normalization, error wrapping) inject a fake
model/processor pair via `ModelManager` so they're fast and don't depend
on real CLIP weights — only real image files on disk (`tmp_path`), since
`Image.open` itself isn't faked. `TestRealClipEmbedding` proves the actual
`transformers`/`torch` wiring works end-to-end against the same tiny test
checkpoint `test_model_manager.py` uses.
"""

from pathlib import Path
from typing import cast

import pytest
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from app.exceptions.errors import EmbeddingGenerationException
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.services.embeddings.clip_service import CLIPEmbeddingService
from app.services.embeddings.model_manager import ModelManager
from app.services.model_registry import ModelRegistry

_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"


class _FakeBatchFeature(dict[str, torch.Tensor]):
    def to(self, device: torch.device) -> "_FakeBatchFeature":
        return self


class _FakePoolingOutput:
    """Mimics the real `BaseModelOutputWithPooling` shape `CLIPEmbeddingService` reads from."""

    def __init__(self, pooler_output: torch.Tensor) -> None:
        self.pooler_output = pooler_output


class _FakeClipModel:
    """Returns a deterministic, non-uniform tensor shaped (batch_size, dimension).

    Implements `.to()`/`.eval()` too — `ModelManager.get_model` calls both
    unconditionally on whatever `model_loader` returns.
    """

    def __init__(self, dimension: int = 4) -> None:
        self.dimension = dimension

    def to(self, device: torch.device) -> "_FakeClipModel":
        return self

    def eval(self) -> "_FakeClipModel":
        return self

    def get_image_features(self, *, pixel_values: torch.Tensor, **_: object) -> _FakePoolingOutput:
        batch_size = pixel_values.shape[0]
        vectors = torch.arange(1, batch_size * self.dimension + 1, dtype=torch.float32).reshape(
            batch_size, self.dimension
        )
        return _FakePoolingOutput(vectors)


class _FakeClipProcessor:
    def __init__(self) -> None:
        self.call_batch_sizes: list[int] = []

    def __call__(self, *, images: list[Image.Image], return_tensors: str) -> _FakeBatchFeature:
        self.call_batch_sizes.append(len(images))
        return _FakeBatchFeature(pixel_values=torch.zeros(len(images), 3, 2, 2))


class _RaisingClipProcessor:
    """A processor stand-in that always fails, to exercise the inference-error path."""

    def __call__(self, *, images: list[Image.Image], return_tensors: str) -> _FakeBatchFeature:
        raise RuntimeError("boom")


def _fake_model_manager(
    *, dimension: int = 4, processor: _FakeClipProcessor | None = None
) -> ModelManager:
    fake_processor = processor if processor is not None else _FakeClipProcessor()
    return ModelManager(
        device="cpu",
        model_loader=lambda name: cast(CLIPModel, _FakeClipModel(dimension=dimension)),
        processor_loader=lambda name: cast(CLIPProcessor, fake_processor),
    )


def _save_image(path: Path, *, size: tuple[int, int] = (10, 10)) -> Path:
    Image.new("RGB", size, (255, 0, 0)).save(path, format="JPEG")
    return path


class TestGenerateEmbedding:
    async def test_returns_a_single_normalized_vector(self, tmp_path: Path) -> None:
        service = CLIPEmbeddingService(
            model_name="fake-model", model_manager=_fake_model_manager(dimension=4)
        )
        image_path = _save_image(tmp_path / "photo.jpg")

        vector = await service.generate_embedding(image_path)

        assert len(vector) == 4
        norm = sum(component**2 for component in vector) ** 0.5
        assert norm == pytest.approx(1.0)

    async def test_raises_embedding_generation_exception_for_a_non_image_file(
        self, tmp_path: Path
    ) -> None:
        service = CLIPEmbeddingService(model_name="fake-model", model_manager=_fake_model_manager())
        bad_path = tmp_path / "not-an-image.jpg"
        bad_path.write_bytes(b"not an image")

        with pytest.raises(EmbeddingGenerationException):
            await service.generate_embedding(bad_path)


class TestGenerateEmbeddings:
    async def test_returns_one_vector_per_input_in_order(self, tmp_path: Path) -> None:
        service = CLIPEmbeddingService(
            model_name="fake-model", model_manager=_fake_model_manager(dimension=4)
        )
        paths = [_save_image(tmp_path / f"photo{i}.jpg") for i in range(3)]

        vectors = await service.generate_embeddings(paths)

        assert len(vectors) == 3
        assert all(len(vector) == 4 for vector in vectors)

    async def test_returns_an_empty_list_for_no_input(self) -> None:
        service = CLIPEmbeddingService(model_name="fake-model", model_manager=_fake_model_manager())

        assert await service.generate_embeddings([]) == []

    async def test_every_vector_is_unit_normalized(self, tmp_path: Path) -> None:
        service = CLIPEmbeddingService(
            model_name="fake-model", model_manager=_fake_model_manager(dimension=6)
        )
        paths = [_save_image(tmp_path / f"photo{i}.jpg") for i in range(2)]

        vectors = await service.generate_embeddings(paths)

        for vector in vectors:
            norm = sum(component**2 for component in vector) ** 0.5
            assert norm == pytest.approx(1.0)

    async def test_chunks_requests_larger_than_the_configured_batch_size(
        self, tmp_path: Path
    ) -> None:
        processor = _FakeClipProcessor()
        service = CLIPEmbeddingService(
            model_name="fake-model",
            batch_size=2,
            model_manager=_fake_model_manager(processor=processor),
        )
        paths = [_save_image(tmp_path / f"photo{i}.jpg") for i in range(5)]

        vectors = await service.generate_embeddings(paths)

        assert len(vectors) == 5
        assert processor.call_batch_sizes == [2, 2, 1]

    async def test_raises_embedding_generation_exception_if_any_image_is_unreadable(
        self, tmp_path: Path
    ) -> None:
        service = CLIPEmbeddingService(model_name="fake-model", model_manager=_fake_model_manager())
        good_path = _save_image(tmp_path / "good.jpg")
        bad_path = tmp_path / "bad.jpg"
        bad_path.write_bytes(b"not an image")

        with pytest.raises(EmbeddingGenerationException):
            await service.generate_embeddings([good_path, bad_path])

    async def test_raises_embedding_generation_exception_when_inference_fails(
        self, tmp_path: Path
    ) -> None:
        model_manager = ModelManager(
            device="cpu",
            model_loader=lambda name: cast(CLIPModel, _FakeClipModel()),
            processor_loader=lambda name: cast(CLIPProcessor, _RaisingClipProcessor()),
        )
        service = CLIPEmbeddingService(model_name="fake-model", model_manager=model_manager)
        image_path = _save_image(tmp_path / "photo.jpg")

        with pytest.raises(EmbeddingGenerationException):
            await service.generate_embedding(image_path)


class TestModelRegistryResolution:
    def test_uses_the_explicit_model_name_when_given_ignoring_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-model",
                version="1.0.0",
                model_type=ModelType.IMAGE_EMBEDDING,
                dimension=512,
                status=ModelStatus.ACTIVE,
            )
        )

        service = CLIPEmbeddingService(model_name="explicit-model", model_registry=registry)

        assert service.model_name == "explicit-model"

    def test_resolves_the_active_image_embedding_model_from_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-clip-model",
                version="1.0.0",
                model_type=ModelType.IMAGE_EMBEDDING,
                dimension=512,
                status=ModelStatus.ACTIVE,
            )
        )

        service = CLIPEmbeddingService(model_registry=registry)

        assert service.model_name == "registry-clip-model"


class TestRealClipEmbedding:
    async def test_generates_a_real_embedding_matching_the_models_projection_dimension(
        self, tmp_path: Path
    ) -> None:
        model_manager = ModelManager(device="cpu")
        model, _processor, _device = model_manager.get_model(_TINY_MODEL_NAME)
        expected_dimension = model.config.projection_dim

        service = CLIPEmbeddingService(model_name=_TINY_MODEL_NAME, model_manager=model_manager)
        image_path = _save_image(tmp_path / "photo.jpg")

        vector = await service.generate_embedding(image_path)

        assert len(vector) == expected_dimension
        norm = sum(component**2 for component in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-4)

    async def test_generates_real_batch_embeddings(self, tmp_path: Path) -> None:
        model_manager = ModelManager(device="cpu")
        service = CLIPEmbeddingService(model_name=_TINY_MODEL_NAME, model_manager=model_manager)
        paths = [_save_image(tmp_path / f"photo{i}.jpg") for i in range(2)]

        vectors = await service.generate_embeddings(paths)

        assert len(vectors) == 2
        assert len(vectors[0]) == len(vectors[1])
