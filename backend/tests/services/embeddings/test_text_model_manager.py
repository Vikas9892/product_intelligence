"""Unit tests for `TextModelManager`.

Most tests inject a fake model loader (fast, deterministic, no network or
real model weights involved) to exercise the caching and thread-safety
logic in isolation — the exact same strategy `test_model_manager.py`
already uses for the image `ModelManager`. `TestRealModelLoading` is the
exception: it loads a genuine, small, widely-cached Sentence Transformers
checkpoint (`sentence-transformers/all-MiniLM-L6-v2` — 384-dimensional,
the same dimension as the default `BAAI/bge-small-en-v1.5`, so it's a
faithful stand-in) to prove the real `sentence-transformers`/`torch`
integration actually works end-to-end.
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest
import torch
from sentence_transformers import SentenceTransformer

from app.services.embeddings.model_manager import resolve_device
from app.services.embeddings.text_model_manager import TextModelManager

_REAL_TINY_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class _FakeTextModel:
    def __init__(self) -> None:
        self.device: torch.device | None = None

    def to(self, device: torch.device) -> "_FakeTextModel":
        self.device = device
        return self


def _fake_model_loader(
    *, load_calls: list[str] | None = None, delay_seconds: float = 0.0
) -> Callable[[str], SentenceTransformer]:
    """Build a fake `model_loader`, optionally recording calls and/or sleeping first."""

    def loader(name: str) -> SentenceTransformer:
        if delay_seconds:
            time.sleep(delay_seconds)
        if load_calls is not None:
            load_calls.append(name)
        return cast(SentenceTransformer, _FakeTextModel())

    return loader


class TestTextModelManagerCaching:
    def test_loads_a_model_only_once_across_repeated_calls(self) -> None:
        load_calls: list[str] = []
        manager = TextModelManager(
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
        manager = TextModelManager(
            device="cpu", model_loader=_fake_model_loader(), metrics_registry=metrics
        )

        manager.get_model("some-model")
        manager.get_model("some-model")

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_model_load_seconds_count", {"model_type": "text_embedding"}
            )
            == 1.0
        )

    def test_caches_different_models_independently(self) -> None:
        load_calls: list[str] = []
        manager = TextModelManager(
            device="cpu", model_loader=_fake_model_loader(load_calls=load_calls)
        )

        manager.get_model("model-a")
        manager.get_model("model-b")
        manager.get_model("model-a")

        assert load_calls == ["model-a", "model-b"]

    def test_places_the_loaded_model_on_the_resolved_device(self) -> None:
        manager = TextModelManager(device="cpu", model_loader=_fake_model_loader())

        model, device = manager.get_model("some-model")
        fake_model = cast(_FakeTextModel, model)

        assert device == torch.device("cpu")
        assert fake_model.device == torch.device("cpu")

    def test_is_loaded_reflects_cache_state(self) -> None:
        manager = TextModelManager(device="cpu", model_loader=_fake_model_loader())

        assert manager.is_loaded("some-model") is False
        manager.get_model("some-model")
        assert manager.is_loaded("some-model") is True


class TestTextModelManagerDeviceResolution:
    def test_reuses_resolve_device_from_the_image_model_manager(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        manager = TextModelManager(device="auto", model_loader=_fake_model_loader())

        _model, device = manager.get_model("some-model")

        assert device == resolve_device("auto") == torch.device("cpu")


class TestTextModelManagerThreadSafety:
    def test_concurrent_requests_for_the_same_model_load_it_only_once(self) -> None:
        load_calls: list[str] = []
        manager = TextModelManager(
            device="cpu",
            model_loader=_fake_model_loader(load_calls=load_calls, delay_seconds=0.05),
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: manager.get_model("shared-model"), range(8)))

        assert load_calls == ["shared-model"]


class TestRealModelLoading:
    def test_loads_a_real_small_sentence_transformer_model(self) -> None:
        manager = TextModelManager(device="cpu")

        model, device = manager.get_model(_REAL_TINY_MODEL_NAME)

        assert isinstance(model, SentenceTransformer)
        assert device == torch.device("cpu")
        assert manager.is_loaded(_REAL_TINY_MODEL_NAME) is True
