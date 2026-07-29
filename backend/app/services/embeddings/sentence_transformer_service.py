"""Sentence-Transformers-based implementation of `BaseTextEmbeddingService`.

Encodes product text (name/brand/category/description, joined — see
`ProductService`) into normalized semantic vectors using a pretrained
Sentence Transformers checkpoint — `TextModelManager` handles loading and
caching the actual model; this class is only responsible for the
encode-and-shape logic, mirroring `CLIPEmbeddingService`'s own division
of responsibility (Phase 4).

Unlike CLIP's `get_image_features`, Sentence Transformers' `.encode(...)`
normalizes natively (`normalize_embeddings=True`) — no separate manual
L2-normalization step is needed the way `CLIPEmbeddingService._encode_batch`
does one.
"""

from starlette.concurrency import run_in_threadpool

from app.core import constants
from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import TextEmbeddingException
from app.models.model_type import ModelType
from app.services.embeddings.text_base import BaseTextEmbeddingService
from app.services.embeddings.text_model_manager import TextModelManager
from app.services.model_registry import ModelRegistry

logger = get_logger(__name__)


class SentenceTransformerEmbeddingService(BaseTextEmbeddingService):
    """Generates Sentence Transformers text embeddings, batching off the event loop."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        batch_size: int | None = None,
        dimension: int | None = None,
        normalize: bool | None = None,
        model_manager: TextModelManager | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        if model_name is not None:
            self._model_name = model_name
        else:
            registry = model_registry if model_registry is not None else ModelRegistry()
            self._model_name = registry.get_active_model(ModelType.TEXT_EMBEDDING).model_name
        self._batch_size = (
            batch_size if batch_size is not None else settings.ai_models.text_batch_size
        )
        # Configured, not introspected from the loaded model: answering
        # "what dimension do you produce?" must not itself force a model
        # load — see `BaseTextEmbeddingService.dimension`'s docstring.
        self._dimension = dimension if dimension is not None else constants.DEFAULT_TEXT_VECTOR_SIZE
        self._normalize = normalize if normalize is not None else settings.ai_models.text_normalize
        self._model_manager = model_manager if model_manager is not None else TextModelManager()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode `texts` in chunks of `batch_size`, preserving input order.

        Chunking bounds how many strings go through one model forward
        pass (memory use) while still batching within that limit — the
        same reasoning `CLIPEmbeddingService.generate_embeddings` already
        documents for images.
        """
        if not texts:
            return []

        logger.info(
            "Generating text embeddings: count=%d, model=%s, batch_size=%d",
            len(texts),
            self._model_name,
            self._batch_size,
        )

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            chunk = texts[start : start + self._batch_size]
            vectors.extend(await run_in_threadpool(self._encode_batch, chunk))

        logger.info(
            "Text embeddings generated: count=%d, dimension=%d",
            len(vectors),
            len(vectors[0]) if vectors else 0,
        )
        return vectors

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        model, _device = self._model_manager.get_model(self._model_name)

        try:
            embeddings = model.encode(
                texts,
                batch_size=len(texts),
                normalize_embeddings=self._normalize,
                convert_to_numpy=True,
            )
        except Exception as exc:
            raise TextEmbeddingException(
                "Model inference failed while generating text embeddings."
            ) from exc

        result: list[list[float]] = embeddings.tolist()
        return result
