"""Loads and caches embedding models so they're loaded exactly once per process.

Loading a CLIP checkpoint is expensive (reading weights from disk/network,
initializing the model on a device) — doing it inside a request handler
would mean every request pays that cost, or worse, concurrent requests
each trigger their own redundant load. `ModelManager` is the seam that
turns "load once at first use, reuse forever" into a property of the
*class*, not something every caller has to remember to implement:

    Application Startup -> (first embedding request) Load Once -> Reuse

Deliberately *not* a request-time singleton the way `get_settings()` is
made one — a `get_model_manager()` cached factory would be redundant
here, since a `ModelManager` only actually needs to exist once because
`CLIPEmbeddingService` (its only caller) is itself constructed exactly
once, as part of the already-cached `get_product_service()` singleton
(`app/dependencies/product.py`). Being constructed once, transitively,
is exactly the same guarantee a dedicated cache would provide, without a
second caching layer to keep in sync with the first.

Model/processor loaders are constructor-injectable (`model_loader`,
`processor_loader`) — the same override pattern every other service in
this codebase uses (`UploadService.upload_dir`, `ImageProcessingService.validator`,
...) — so tests can substitute a fast fake instead of downloading real
CLIP weights, while production code gets the real
`CLIPModel.from_pretrained`/`CLIPProcessor.from_pretrained` by default.
"""

import threading
import time
from collections.abc import Callable

import torch
from transformers import CLIPModel, CLIPProcessor

from app.core.config import settings
from app.core.logging import get_logger
from app.metrics.metrics_registry import MetricsRegistry

logger = get_logger(__name__)

#: One loaded model, its processor, and the device it was placed on.
LoadedModel = tuple[CLIPModel, CLIPProcessor, torch.device]


def resolve_device(preference: str) -> torch.device:
    """Resolve a device preference ("auto", "cpu", "cuda", "cuda:0", ...) to a `torch.device`.

    `"auto"` picks CUDA if available, else CPU — anything else is passed
    straight to `torch.device`, so an operator can force a specific device
    (e.g. to pin a multi-GPU host to `"cuda:1"`) without this function
    needing to know every possible device string in advance.
    """
    if preference == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(preference)


class ModelManager:
    """Lazily loads embedding models, caching each by name for the instance's lifetime.

    Thread-safe: `get_model` uses double-checked locking so concurrent
    callers requesting the same not-yet-loaded model only trigger one
    real load (the rest wait for and then reuse it), while callers
    requesting an *already*-loaded model never contend on the lock at all.
    """

    def __init__(
        self,
        *,
        device: str | None = None,
        model_loader: Callable[[str], CLIPModel] | None = None,
        processor_loader: Callable[[str], CLIPProcessor] | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._device = resolve_device(
            device if device is not None else settings.ai_models.embedding_device
        )
        self._model_loader = model_loader if model_loader is not None else CLIPModel.from_pretrained
        self._processor_loader = (
            processor_loader if processor_loader is not None else CLIPProcessor.from_pretrained
        )
        self._models: dict[str, LoadedModel] = {}
        self._lock = threading.Lock()
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    def get_model(self, model_name: str) -> LoadedModel:
        """Return `(model, processor, device)` for `model_name`, loading it on first use."""
        cached = self._models.get(model_name)
        if cached is not None:
            return cached

        with self._lock:
            # Re-check inside the lock: another thread may have finished
            # loading this exact model while we were waiting to acquire it.
            cached = self._models.get(model_name)
            if cached is None:
                logger.info(
                    "Loading embedding model '%s' onto device '%s'", model_name, self._device
                )
                load_start = time.monotonic()
                model = self._model_loader(model_name)
                # torch's `nn.Module.to()` type stub is imprecise about its
                # heavily-overloaded signature (device, dtype, tensor, or
                # combinations) — passing a `torch.device` here is correct
                # at runtime per PyTorch's own documented API.
                model = model.to(self._device)  # type: ignore[arg-type]
                model.eval()
                processor = self._processor_loader(model_name)
                cached = (model, processor, self._device)
                self._models[model_name] = cached
                self._metrics.observe_model_load(
                    model_type="image_embedding", seconds=time.monotonic() - load_start
                )
                logger.info("Embedding model '%s' loaded", model_name)

        return cached

    def is_loaded(self, model_name: str) -> bool:
        """Return whether `model_name` has already been loaded (no locking needed to check)."""
        return model_name in self._models
