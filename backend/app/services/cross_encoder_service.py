"""`CrossEncoderService`: scores query-document pairs with a cross-encoder model.

Unlike `CLIPEmbeddingService`/`SentenceTransformerEmbeddingService` (which
encode a query and a document *independently* into vectors, then compare
those vectors with cosine similarity), a cross-encoder feeds the query
and document into the model *together*, letting it attend across both at
once — slower per pair (no vector can be precomputed and reused across
queries), but typically a more accurate relevance judgment, which is
exactly why it's used to refine an already-retrieved candidate pool
rather than to search a whole catalog from scratch.

This class only scores pairs — it has no opinion about ranking, cutoffs,
or which candidates to score in the first place (that's
`RerankerService`'s job, Milestone 3). Mirrors
`SentenceTransformerEmbeddingService`'s own division of responsibility:
`ModelManagerCrossEncoder` handles lazy loading/caching, this class is
only responsible for the batch-and-score logic, and inference is pushed
off the event loop the same way `embed_batch` already does.

`score_pairs` returns plain `float`s, never a raw `torch.Tensor`/`numpy`
array — the "never expose raw model outputs" requirement.
"""

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import RerankException
from app.models.model_type import ModelType
from app.services.model_manager_cross_encoder import ModelManagerCrossEncoder
from app.services.model_registry import ModelRegistry

logger = get_logger(__name__)

#: One (query, document) pair to be scored for relevance.
Pair = tuple[str, str]


class CrossEncoderService:
    """Scores query-document pairs in batches using a cross-encoder model."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        batch_size: int | None = None,
        model_manager: ModelManagerCrossEncoder | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        if model_name is not None:
            self._model_name = model_name
        else:
            registry = model_registry if model_registry is not None else ModelRegistry()
            self._model_name = registry.get_active_model(ModelType.RERANKER).model_name
        self._batch_size = batch_size if batch_size is not None else settings.reranker.batch_size
        self._model_manager = (
            model_manager if model_manager is not None else ModelManagerCrossEncoder()
        )

    async def score_pairs(self, pairs: list[Pair]) -> list[float]:
        """Score each `(query, document)` pair, returning one relevance score per pair, in order.

        Chunks `pairs` into `batch_size`-sized groups before each model
        forward pass — the same reasoning `SentenceTransformerEmbeddingService.
        embed_batch` already documents for images/text. Raises
        `RerankException` if inference fails.
        """
        if not pairs:
            return []

        logger.info(
            "Scoring cross-encoder pairs: count=%d, model=%s, batch_size=%d",
            len(pairs),
            self._model_name,
            self._batch_size,
        )

        scores: list[float] = []
        for start in range(0, len(pairs), self._batch_size):
            chunk = pairs[start : start + self._batch_size]
            scores.extend(await run_in_threadpool(self._predict_batch, chunk))

        logger.info("Cross-encoder scoring complete: count=%d", len(scores))
        return scores

    def _predict_batch(self, pairs: list[Pair]) -> list[float]:
        model, _device = self._model_manager.get_model(self._model_name)

        try:
            # `CrossEncoder.predict`'s type stub covers its full multimodal
            # (text/image/audio/video) input space, which mypy can't match
            # a plain `list[tuple[str, str]]` against precisely — text-pair
            # scoring is a documented, correct usage of this API at runtime.
            raw_scores = model.predict(pairs, batch_size=len(pairs), convert_to_numpy=True)  # type: ignore[arg-type]
        except Exception as exc:
            raise RerankException("Cross-encoder inference failed while scoring pairs.") from exc

        return [float(score) for score in raw_scores]
