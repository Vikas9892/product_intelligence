"""Loads and caches cross-encoder reranking models so they're loaded exactly once per process.

Mirrors `app.services.embeddings.text_model_manager.TextModelManager`
almost exactly — same "load once at first use, reuse forever" reasoning,
same double-checked-locking thread safety, same constructor-injectable
loader for tests. Reuses `resolve_device` directly rather than
redefining it, the same reasoning `TextModelManager` already established
for reusing it from `app.services.embeddings.model_manager`.

Kept at `app/services/` (not nested under `app/services/embeddings/`)
because a cross-encoder reranker isn't an embedding model — it never
produces a vector, only a relevance score for a query-document pair — so
grouping it with the embedding model managers would misdescribe what it
does.
"""

import threading
from collections.abc import Callable

import torch
from sentence_transformers import CrossEncoder

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embeddings.model_manager import resolve_device

logger = get_logger(__name__)

#: One loaded cross-encoder model and the device it was placed on.
LoadedCrossEncoder = tuple[CrossEncoder, torch.device]


class ModelManagerCrossEncoder:
    """Lazily loads cross-encoder models, caching each by name for the instance's lifetime.

    Thread-safe: `get_model` uses double-checked locking so concurrent
    callers requesting the same not-yet-loaded model only trigger one
    real load (the rest wait for and then reuse it), while callers
    requesting an *already*-loaded model never contend on the lock at all
    — identical shape to `TextModelManager.get_model`.
    """

    def __init__(
        self,
        *,
        device: str | None = None,
        model_loader: Callable[..., CrossEncoder] | None = None,
    ) -> None:
        self._device = resolve_device(device if device is not None else settings.reranker.device)
        self._model_loader = model_loader if model_loader is not None else CrossEncoder
        self._models: dict[str, LoadedCrossEncoder] = {}
        self._lock = threading.Lock()

    def get_model(self, model_name: str) -> LoadedCrossEncoder:
        """Return `(model, device)` for `model_name`, loading it on first use."""
        cached = self._models.get(model_name)
        if cached is not None:
            return cached

        with self._lock:
            # Re-check inside the lock: another thread may have finished
            # loading this exact model while we were waiting to acquire it.
            cached = self._models.get(model_name)
            if cached is None:
                logger.info(
                    "Loading cross-encoder model '%s' onto device '%s'", model_name, self._device
                )
                # Unlike `CLIPModel`/`SentenceTransformer` (loaded, then moved
                # onto a device via `.to()`), `CrossEncoder` places itself on
                # its target device as part of construction.
                model = self._model_loader(model_name, device=str(self._device))
                cached = (model, self._device)
                self._models[model_name] = cached
                logger.info("Cross-encoder model '%s' loaded", model_name)

        return cached

    def is_loaded(self, model_name: str) -> bool:
        """Return whether `model_name` has already been loaded (no locking needed to check)."""
        return model_name in self._models
