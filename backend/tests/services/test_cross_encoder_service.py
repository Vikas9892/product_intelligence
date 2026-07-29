"""Unit tests for `CrossEncoderService`.

Logic tests (batching, error wrapping) inject a fake model via
`ModelManagerCrossEncoder` so they're fast and don't depend on real model
weights — the same strategy `test_sentence_transformer_service.py` uses.
`TestRealCrossEncoderScoring` proves the actual `sentence-transformers`
wiring works end-to-end against a real, tiny, widely-cached checkpoint.
"""

from typing import cast

import numpy as np
import pytest
from sentence_transformers import CrossEncoder

from app.exceptions.errors import RerankException
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.services.cross_encoder_service import CrossEncoderService
from app.services.model_manager_cross_encoder import ModelManagerCrossEncoder
from app.services.model_registry import ModelRegistry

_REAL_TINY_MODEL_NAME = "cross-encoder/ms-marco-TinyBERT-L-2-v2"


class _FakeCrossEncoderModel:
    """Returns a deterministic score per pair (its index in the batch)."""

    def __init__(self) -> None:
        self.predict_batch_sizes: list[int] = []

    def predict(
        self, pairs: list[tuple[str, str]], *, batch_size: int, convert_to_numpy: bool
    ) -> np.ndarray:
        self.predict_batch_sizes.append(len(pairs))
        return np.arange(len(pairs), dtype=np.float32)


class _RaisingCrossEncoderModel:
    def predict(self, pairs: list[tuple[str, str]], **kwargs: object) -> np.ndarray:
        raise RuntimeError("boom")


def _fake_model_manager(
    *, model: _FakeCrossEncoderModel | _RaisingCrossEncoderModel | None = None
) -> ModelManagerCrossEncoder:
    fake_model = model if model is not None else _FakeCrossEncoderModel()
    return ModelManagerCrossEncoder(
        device="cpu",
        model_loader=lambda name, **kwargs: cast(CrossEncoder, fake_model),
    )


class TestScorePairs:
    async def test_returns_one_score_per_pair_in_order(self) -> None:
        service = CrossEncoderService(model_name="fake-model", model_manager=_fake_model_manager())

        scores = await service.score_pairs([("q", "a"), ("q", "b"), ("q", "c")])

        assert scores == [0.0, 1.0, 2.0]

    async def test_returns_an_empty_list_for_no_pairs(self) -> None:
        service = CrossEncoderService(model_name="fake-model", model_manager=_fake_model_manager())

        assert await service.score_pairs([]) == []

    async def test_returns_plain_floats_not_a_raw_numpy_array(self) -> None:
        service = CrossEncoderService(model_name="fake-model", model_manager=_fake_model_manager())

        scores = await service.score_pairs([("q", "a")])

        assert all(isinstance(score, float) for score in scores)

    async def test_chunks_requests_larger_than_the_configured_batch_size(self) -> None:
        fake_model = _FakeCrossEncoderModel()
        service = CrossEncoderService(
            model_name="fake-model",
            batch_size=2,
            model_manager=_fake_model_manager(model=fake_model),
        )

        scores = await service.score_pairs(
            [("q", "a"), ("q", "b"), ("q", "c"), ("q", "d"), ("q", "e")]
        )

        assert len(scores) == 5
        assert fake_model.predict_batch_sizes == [2, 2, 1]

    async def test_raises_rerank_exception_on_inference_failure(self) -> None:
        service = CrossEncoderService(
            model_name="fake-model",
            model_manager=_fake_model_manager(model=_RaisingCrossEncoderModel()),
        )

        with pytest.raises(RerankException):
            await service.score_pairs([("q", "a")])


class TestCrossEncoderServiceDefaults:
    def test_model_name_defaults_to_settings(self) -> None:
        service = CrossEncoderService(model_manager=_fake_model_manager())

        assert service._model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def test_batch_size_defaults_to_settings(self) -> None:
        service = CrossEncoderService(model_manager=_fake_model_manager())

        assert service._batch_size == 16


class TestModelRegistryResolution:
    def test_uses_the_explicit_model_name_when_given_ignoring_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-model",
                version="1.0.0",
                model_type=ModelType.RERANKER,
                dimension=1,
                status=ModelStatus.ACTIVE,
            )
        )

        service = CrossEncoderService(model_name="explicit-model", model_registry=registry)

        assert service._model_name == "explicit-model"

    def test_resolves_the_active_reranker_model_from_the_registry(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(
            ModelInfo(
                model_name="registry-reranker-model",
                version="1.0.0",
                model_type=ModelType.RERANKER,
                dimension=1,
                status=ModelStatus.ACTIVE,
            )
        )

        service = CrossEncoderService(model_registry=registry)

        assert service._model_name == "registry-reranker-model"


class TestRealCrossEncoderScoring:
    async def test_scores_a_real_relevant_pair_higher_than_an_irrelevant_one(self) -> None:
        model_manager = ModelManagerCrossEncoder(device="cpu")
        service = CrossEncoderService(model_name=_REAL_TINY_MODEL_NAME, model_manager=model_manager)

        scores = await service.score_pairs(
            [
                ("red running shoes", "Nike red running shoes for athletes"),
                ("red running shoes", "a wooden dining table"),
            ]
        )

        assert len(scores) == 2
        assert all(isinstance(score, float) for score in scores)
        assert scores[0] > scores[1]
