"""Unit tests for `ModelManager`.

Most tests inject fake model/processor loaders (fast, deterministic, no
network or real model weights involved) to exercise the caching and
thread-safety logic in isolation. Each fake is `cast()` to the real
`CLIPModel`/`CLIPProcessor` type at the point it's handed to `ModelManager`
— that's the actual contract `model_loader`/`processor_loader` promise,
and a fake test double that doesn't (and needn't) replicate either
class's full surface area is the standard way to satisfy that statically
without weakening `ModelManager`'s own type hints for production callers.

`TestRealModelLoading` is the exception: it loads a genuine (but tiny,
randomly-initialized) CLIP checkpoint from the Hugging Face Hub —
`hf-internal-testing/tiny-random-CLIPModel`, a model published
specifically for fast test suites — to prove the real
`transformers`/`torch` integration actually works end-to-end, not just
our own caching logic around it.
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest
import torch
from transformers import CLIPModel, CLIPProcessor

from app.services.embeddings.model_manager import ModelManager, resolve_device

_TINY_MODEL_NAME = "hf-internal-testing/tiny-random-CLIPModel"


class _FakeModel:
    def __init__(self) -> None:
        self.device: torch.device | None = None
        self.eval_called = False

    def to(self, device: torch.device) -> "_FakeModel":
        self.device = device
        return self

    def eval(self) -> "_FakeModel":
        self.eval_called = True
        return self


class _FakeProcessor:
    pass


def _fake_model_loader(
    *, load_calls: list[str] | None = None, delay_seconds: float = 0.0
) -> Callable[[str], CLIPModel]:
    """Build a fake `model_loader`, optionally recording calls and/or sleeping first."""

    def loader(name: str) -> CLIPModel:
        if delay_seconds:
            time.sleep(delay_seconds)
        if load_calls is not None:
            load_calls.append(name)
        return cast(CLIPModel, _FakeModel())

    return loader


def _fake_processor_loader(name: str) -> CLIPProcessor:
    return cast(CLIPProcessor, _FakeProcessor())


class TestResolveDevice:
    def test_auto_prefers_cuda_when_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        assert resolve_device("auto") == torch.device("cuda")

    def test_auto_falls_back_to_cpu_when_cuda_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        assert resolve_device("auto") == torch.device("cpu")

    def test_explicit_device_is_passed_through(self) -> None:
        assert resolve_device("cpu") == torch.device("cpu")


class TestModelManagerCaching:
    def test_loads_a_model_only_once_across_repeated_calls(self) -> None:
        load_calls: list[str] = []
        manager = ModelManager(
            device="cpu",
            model_loader=_fake_model_loader(load_calls=load_calls),
            processor_loader=_fake_processor_loader,
        )

        manager.get_model("some-model")
        manager.get_model("some-model")
        manager.get_model("some-model")

        assert load_calls == ["some-model"]

    def test_caches_different_models_independently(self) -> None:
        load_calls: list[str] = []
        manager = ModelManager(
            device="cpu",
            model_loader=_fake_model_loader(load_calls=load_calls),
            processor_loader=_fake_processor_loader,
        )

        manager.get_model("model-a")
        manager.get_model("model-b")
        manager.get_model("model-a")

        assert load_calls == ["model-a", "model-b"]

    def test_places_the_loaded_model_on_the_resolved_device(self) -> None:
        manager = ModelManager(
            device="cpu",
            model_loader=_fake_model_loader(),
            processor_loader=_fake_processor_loader,
        )

        model, _processor, device = manager.get_model("some-model")
        fake_model = cast(_FakeModel, model)

        assert device == torch.device("cpu")
        assert fake_model.device == torch.device("cpu")
        assert fake_model.eval_called is True

    def test_is_loaded_reflects_cache_state(self) -> None:
        manager = ModelManager(
            device="cpu",
            model_loader=_fake_model_loader(),
            processor_loader=_fake_processor_loader,
        )

        assert manager.is_loaded("some-model") is False
        manager.get_model("some-model")
        assert manager.is_loaded("some-model") is True


class TestModelManagerThreadSafety:
    def test_concurrent_requests_for_the_same_model_load_it_only_once(self) -> None:
        load_calls: list[str] = []
        manager = ModelManager(
            device="cpu",
            # A small delay widens the race window a broken (unlocked)
            # implementation would need to actually exhibit double-loading.
            model_loader=_fake_model_loader(load_calls=load_calls, delay_seconds=0.05),
            processor_loader=_fake_processor_loader,
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: manager.get_model("shared-model"), range(8)))

        assert load_calls == ["shared-model"]


class TestRealModelLoading:
    def test_loads_a_real_tiny_clip_model(self) -> None:
        manager = ModelManager(device="cpu")

        model, processor, device = manager.get_model(_TINY_MODEL_NAME)

        assert isinstance(model, CLIPModel)
        assert isinstance(processor, CLIPProcessor)
        assert device == torch.device("cpu")
        assert manager.is_loaded(_TINY_MODEL_NAME) is True
