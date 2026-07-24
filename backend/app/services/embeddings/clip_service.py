"""CLIP-based implementation of `BaseEmbeddingService`.

Encodes already-processed images (standardized RGB JPEGs from
`ImageProcessingService`, Phase 3) into normalized semantic vectors using
a pretrained CLIP vision encoder — `ModelManager` handles loading and
caching the actual model/processor; this class is only responsible for
the encode-and-normalize logic and shaping the result as plain Python
lists of floats (never a framework-specific tensor type) for anything
downstream of this layer to consume.
"""

from pathlib import Path

import torch
from PIL import Image
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import EmbeddingGenerationException
from app.services.embeddings.base import BaseEmbeddingService
from app.services.embeddings.model_manager import ModelManager

logger = get_logger(__name__)


class CLIPEmbeddingService(BaseEmbeddingService):
    """Generates CLIP image embeddings, batching and running inference off the event loop."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        batch_size: int | None = None,
        model_manager: ModelManager | None = None,
    ) -> None:
        self._model_name = (
            model_name if model_name is not None else settings.ai_models.clip_model_name
        )
        self._batch_size = (
            batch_size if batch_size is not None else settings.ai_models.embedding_batch_size
        )
        self._model_manager = model_manager if model_manager is not None else ModelManager()

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_embedding(self, image_path: Path) -> list[float]:
        vectors = await self.generate_embeddings([image_path])
        return vectors[0]

    async def generate_embeddings(self, image_paths: list[Path]) -> list[list[float]]:
        """Encode `image_paths` in chunks of `batch_size`, preserving input order.

        Chunking bounds how many images go through one model forward pass
        (memory use) while still batching within that limit (fewer,
        larger inference calls instead of one-by-one) — the whole point
        of exposing a batch method separately from `generate_embedding`.
        """
        if not image_paths:
            return []

        logger.info(
            "Generating embeddings: count=%d, model=%s, batch_size=%d",
            len(image_paths),
            self._model_name,
            self._batch_size,
        )

        vectors: list[list[float]] = []
        for start in range(0, len(image_paths), self._batch_size):
            chunk = image_paths[start : start + self._batch_size]
            vectors.extend(await run_in_threadpool(self._encode_batch, chunk))

        logger.info(
            "Embeddings generated: count=%d, dimension=%d",
            len(vectors),
            len(vectors[0]) if vectors else 0,
        )
        return vectors

    def _encode_batch(self, image_paths: list[Path]) -> list[list[float]]:
        model, processor, device = self._model_manager.get_model(self._model_name)

        try:
            images = [Image.open(path).convert("RGB") for path in image_paths]
        except Exception as exc:
            raise EmbeddingGenerationException(
                "Failed to open one or more images for embedding generation."
            ) from exc

        try:
            inputs = processor(images=images, return_tensors="pt").to(device)
            with torch.no_grad():
                # `get_image_features` returns a `BaseModelOutputWithPooling`
                # in this transformers version, not a bare tensor — the
                # projected image embedding (after CLIP's visual
                # projection layer) lives at `.pooler_output`.
                image_features = model.get_image_features(**inputs).pooler_output
            # L2-normalize so downstream cosine similarity (semantic
            # search, duplicate detection — later phases) reduces to a
            # plain dot product between vectors.
            normalized = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        except EmbeddingGenerationException:
            raise
        except Exception as exc:
            raise EmbeddingGenerationException(
                "Model inference failed while generating embeddings."
            ) from exc

        result: list[list[float]] = normalized.cpu().tolist()
        return result
