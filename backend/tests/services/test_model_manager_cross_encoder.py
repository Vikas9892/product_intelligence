"""Unit tests for `ModelManagerCrossEncoder`.

Mirrors `tests/services/embeddings/test_text_model_manager.py` exactly:
a fake loader for the caching/thread-safety logic, `TestRealModelLoading`
for the genuine `sentence-transformers` wiring, using a real, tiny,
widely-cached cross-encoder checkpoint.
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest
import torch
from sentence_transformers import CrossEncoder

from app.services.embeddings.model_manager import resolve_device
from app.services.model_manager_cross_encoder import ModelManagerCrossEncoder

_REAL_TINY_MODEL_NAME = "cross-encoder/ms-marco-TinyBERT-L-2-v2"


class _FakeCrossEncoderModel:
    def __init__(self, *, device: str | None = None) -> None:
        self.device = device


def _fake_model_loader(
    *, load_calls: list[str] | None = None, delay_seconds: float = 0.0
) -> Callable[..., CrossEncoder]:
    """Build a fake `model_loader`, optionally recording calls and/or sleeping first."""

    def loader(name: str, *, device: str | None = None) -> CrossEncoder:
        if delay_seconds:
            time.sleep(delay_seconds)
        if load_calls is not None:
            load_calls.append(name)
        return cast(CrossEncoder, _FakeCrossEncoderModel(device=device))

    return loader


class TestModelManagerCrossEncoderCaching:
    def test_loads_a_model_only_once_across_repeated_calls(self) -> None:
        load_calls: list[str] = []
        manager = ModelManagerCrossEncoder(
            device="cpu", model_loader=_fake_model_loader(load_calls=load_calls)
        )

        manager.get_model("some-model")
        manager.get_model("some-model")
        manager.get_model("some-model")

        assert load_calls == ["some-model"]

    def test_records_model_load_time_on_first_load_only(self) -> None:
        from prometheus_client import CollectorRegistry

        from app.metrics.metrics_registry import MetricsRegistry

        metrics = MetricsRegistry(registry=CollectorRegistry())
        manager = ModelManagerCrossEncoder(
            device="cpu", model_loader=_fake_model_loader(), metrics_registry=metrics
        )

        manager.get_model("some-model")
        manager.get_model("some-model")

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_model_load_seconds_count", {"model_type": "reranker"}
            )
            == 1.0
        )

    def test_caches_different_models_independently(self) -> None:
        load_calls: list[str] = []
        manager = ModelManagerCrossEncoder(
            device="cpu", model_loader=_fake_model_loader(load_calls=load_calls)
        )

        manager.get_model("model-a")
        manager.get_model("model-b")
        manager.get_model("model-a")

        assert load_calls == ["model-a", "model-b"]

    def test_loads_the_model_onto_the_resolved_device(self) -> None:
        manager = ModelManagerCrossEncoder(device="cpu", model_loader=_fake_model_loader())

        model, device = manager.get_model("some-model")
        fake_model = cast(_FakeCrossEncoderModel, model)

        assert device == torch.device("cpu")
        assert fake_model.device == "cpu"

    def test_is_loaded_reflects_cache_state(self) -> None:
        manager = ModelManagerCrossEncoder(device="cpu", model_loader=_fake_model_loader())

        assert manager.is_loaded("some-model") is False
        manager.get_model("some-model")
        assert manager.is_loaded("some-model") is True


class _WarmupRecordingModel:
    """Records `predict` calls so a test can prove warm-up ran (or didn't)."""

    def __init__(self, *, device: str | None = None, raises: bool = False) -> None:
        self.device = device
        self._raises = raises
        self.predict_calls: list[object] = []

    def predict(self, pairs: object, **_: object) -> list[float]:
        self.predict_calls.append(pairs)
        if self._raises:
            raise RuntimeError("warmup boom")
        return [0.0]


class TestModelManagerCrossEncoderWarmup:
    def test_no_warmup_inference_when_disabled(self) -> None:
        model = _WarmupRecordingModel()
        manager = ModelManagerCrossEncoder(
            device="cpu",
            model_loader=lambda name, **kwargs: cast(CrossEncoder, model),
            warmup_enabled=False,
        )

        manager.get_model("some-model")

        assert model.predict_calls == []

    def test_runs_one_warmup_inference_when_enabled(self) -> None:
        model = _WarmupRecordingModel()
        manager = ModelManagerCrossEncoder(
            device="cpu",
            model_loader=lambda name, **kwargs: cast(CrossEncoder, model),
            warmup_enabled=True,
        )

        manager.get_model("some-model")
        manager.get_model("some-model")  # cached: no second warm-up

        assert len(model.predict_calls) == 1

    def test_a_warmup_failure_is_non_fatal(self) -> None:
        model = _WarmupRecordingModel(raises=True)
        manager = ModelManagerCrossEncoder(
            device="cpu",
            model_loader=lambda name, **kwargs: cast(CrossEncoder, model),
            warmup_enabled=True,
        )

        # The load still succeeds and the model is cached despite warm-up raising.
        manager.get_model("some-model")

        assert model.predict_calls != []  # warm-up was attempted
        assert manager.is_loaded("some-model") is True


class TestModelManagerCrossEncoderDeviceResolution:
    def test_reuses_resolve_device_from_the_image_model_manager(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        manager = ModelManagerCrossEncoder(device="auto", model_loader=_fake_model_loader())

        _model, device = manager.get_model("some-model")

        assert device == resolve_device("auto") == torch.device("cpu")


class TestModelManagerCrossEncoderThreadSafety:
    def test_concurrent_requests_for_the_same_model_load_it_only_once(self) -> None:
        load_calls: list[str] = []
        manager = ModelManagerCrossEncoder(
            device="cpu",
            model_loader=_fake_model_loader(load_calls=load_calls, delay_seconds=0.05),
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: manager.get_model("shared-model"), range(8)))

        assert load_calls == ["shared-model"]


class TestRealModelLoading:
    def test_loads_a_real_small_cross_encoder_model(self) -> None:
        manager = ModelManagerCrossEncoder(device="cpu")

        model, device = manager.get_model(_REAL_TINY_MODEL_NAME)

        assert isinstance(model, CrossEncoder)
        assert device == torch.device("cpu")
        assert manager.is_loaded(_REAL_TINY_MODEL_NAME) is True
