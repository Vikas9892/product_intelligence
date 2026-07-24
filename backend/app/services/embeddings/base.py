"""Embedding generation abstraction.

`BaseEmbeddingService` is the interface `ProductService` depends on — not
`CLIPEmbeddingService` directly. Today's only implementation encodes
images with CLIP; swapping in DINOv2, SigLIP, or any future encoder later
means writing one new class that satisfies this interface, with nothing
outside `app/services/embeddings/` needing to change. This is the same
"depend on the seam, not the concrete implementation" reasoning that
already shapes `BaseEmbeddingService`'s sibling abstractions in this
codebase (e.g. `app.validators.*` as pure functions `UploadService`/
`ProductService` call into, rather than deciding rules themselves).

Both methods are `async def` — matching every other service in this
codebase (`UploadService`, `ChecksumService`, `ImageProcessingService`) —
even though a concrete implementation's actual model inference is
blocking, CPU/GPU-bound work. Callers should never need to know or care
whether "generate an embedding" happens to block a thread internally;
`Depends()`-injected services in this codebase are uniformly awaitable.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseEmbeddingService(ABC):
    """Interface for turning an image file into a semantic embedding vector."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the identifier of the model that produces this service's embeddings.

        Exposed so callers (`ProductService`, building an `ImageEmbedding`)
        can record which model actually generated a given vector without
        having to duplicate or guess it from settings — the service that
        did the encoding is the only source of truth for that.
        """
        raise NotImplementedError

    @abstractmethod
    async def generate_embedding(self, image_path: Path) -> list[float]:
        """Return the embedding vector for the image at `image_path`."""
        raise NotImplementedError

    @abstractmethod
    async def generate_embeddings(self, image_paths: list[Path]) -> list[list[float]]:
        """Return one embedding vector per path in `image_paths`, in the same order.

        Implementations should batch the underlying model calls where
        possible rather than looping `generate_embedding` — that's the
        entire reason this exists as a separate method instead of callers
        just calling `generate_embedding` in a loop themselves.
        """
        raise NotImplementedError
