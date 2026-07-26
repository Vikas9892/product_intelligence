"""Text embedding generation abstraction.

`BaseTextEmbeddingService` is the interface `ProductService`/`TextSearchService`
depend on — not `SentenceTransformerEmbeddingService` directly. This is the
same "depend on the seam, not the concrete implementation" reasoning that
already shapes `BaseEmbeddingService` (Phase 4, image embeddings); the two
are deliberately separate interfaces rather than one shared abstraction,
since embedding a piece of text and embedding an image file are different
operations with different inputs (`str` vs. `Path`) — forcing them under
one interface would mean one side always ignoring parameters meant for
the other.

`model_name`/`dimension` are properties, not zero-argument methods (the
phase spec writes `model_name()`/`dimension()`) — matching the
established convention `BaseEmbeddingService.model_name` already set in
Phase 4, and `dimension` in particular must be answerable without
triggering a model load (see `SentenceTransformerEmbeddingService`'s own
docstring for why), which reads more naturally as a property than a
method that happens to do no work.

Both `embed_text`/`embed_batch` are `async def`, matching every other
service in this codebase, even though a concrete implementation's actual
model inference is blocking, CPU/GPU-bound work.
"""

from abc import ABC, abstractmethod


class BaseTextEmbeddingService(ABC):
    """Interface for turning text into a semantic embedding vector."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the identifier of the model that produces this service's embeddings."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the length of every vector this service produces."""
        raise NotImplementedError

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for `text`."""
        raise NotImplementedError

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per string in `texts`, in the same order.

        Implementations should batch the underlying model calls where
        possible rather than looping `embed_text` — that's the entire
        reason this exists as a separate method instead of callers just
        calling `embed_text` in a loop themselves.
        """
        raise NotImplementedError
