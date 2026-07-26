"""Loads and caches text embedding models so they're loaded exactly once per process.

Mirrors `app.services.embeddings.model_manager.ModelManager` (Phase 4)
almost exactly — same "load once at first use, reuse forever" reasoning,
same double-checked-locking thread safety, same constructor-injectable
loader for tests. Reuses that module's `resolve_device` directly rather
than redefining it: resolving a device string ("auto"/"cpu"/"cuda[:N]")
to a `torch.device` has nothing image-specific about it, so duplicating
it here would be the exact kind of logic duplication this codebase
avoids elsewhere.

Deliberately *not* a request-time singleton the way `get_settings()` is
made one, for the same reason `ModelManager` isn't: a `TextModelManager`
only actually needs to exist once because `SentenceTransformerEmbeddingService`
(its only caller) is itself constructed exactly once, as part of an
already-cached service singleton.
"""

import threading
from collections.abc import Callable

import torch
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embeddings.model_manager import resolve_device

logger = get_logger(__name__)

#: One loaded text model and the device it was placed on.
LoadedTextModel = tuple[SentenceTransformer, torch.device]


class TextModelManager:
    """Lazily loads text embedding models, caching each by name for the instance's lifetime.

    Thread-safe: `get_model` uses double-checked locking so concurrent
    callers requesting the same not-yet-loaded model only trigger one
    real load (the rest wait for and then reuse it), while callers
    requesting an *already*-loaded model never contend on the lock at all
    — identical shape to `ModelManager.get_model`.
    """

    def __init__(
        self,
        *,
        device: str | None = None,
        model_loader: Callable[[str], SentenceTransformer] | None = None,
    ) -> None:
        self._device = resolve_device(
            device if device is not None else settings.ai_models.text_device
        )
        self._model_loader = model_loader if model_loader is not None else SentenceTransformer
        self._models: dict[str, LoadedTextModel] = {}
        self._lock = threading.Lock()

    def get_model(self, model_name: str) -> LoadedTextModel:
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
                    "Loading text embedding model '%s' onto device '%s'",
                    model_name,
                    self._device,
                )
                model = self._model_loader(model_name)
                # Unlike `ModelManager`'s `CLIPModel.to()`, `SentenceTransformer`'s
                # own stub for `.to()` is precise about accepting a `torch.device`
                # here — no `type: ignore` needed.
                model = model.to(self._device)
                cached = (model, self._device)
                self._models[model_name] = cached
                logger.info("Text embedding model '%s' loaded", model_name)

        return cached

    def is_loaded(self, model_name: str) -> bool:
        """Return whether `model_name` has already been loaded (no locking needed to check)."""
        return model_name in self._models
