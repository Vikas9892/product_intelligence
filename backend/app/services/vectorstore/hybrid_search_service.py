"""Hybrid search service: orchestrates image search, text search, and score fusion.

Deliberately *not* built by turning `SearchService` into a "hybrid"
service that also knows about text — that would give one class two
unrelated responsibilities (image-only search, and score fusion across
modalities) and make each harder to test or extend independently.
Instead: `SearchService` stays image-only, `TextSearchService` stays
text-only, and `HybridSearchService` composes both plus its own fusion
logic. Which query modalities are actually provided determines the
behavior:

- Image only: run the image search, return its own scores/ranking as-is.
- Text only: run the text search, return its own scores/ranking as-is.
- Both: run both searches, merge candidates by `product_id`, and compute
  `final_score = image_weight * image_score + text_weight * text_score`
  (`app.core.settings.HybridSearchSettings`) — a candidate present on only
  one side contributes zero for the side it's missing from, per the
  phase's fusion rule.

Returning a single-modality's raw score unweighted (rather than always
multiplying by its configured weight) is deliberate: a caller searching
by image only expects scores that reflect image similarity directly, not
silently deflated by `IMAGE_WEIGHT` — the weights only make sense as a
*relative* balance between two modalities actually being combined.

Both sub-searches are asked for the same `top_k` the caller requested,
not an inflated candidate pool — a candidate ranking outside `top_k` on
*both* individual searches can never surface after fusion even if it
would have scored well combined. Over-fetching to guard against that is a
real hybrid-search refinement, but it's a ranking-quality tuning knob
this phase doesn't ask for (see "Explicitly Excluded: Learning-to-rank"),
so it's left as a documented limitation rather than an undiscussed
implementation choice.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import (
    HybridSearchException,
    ResourceNotFoundException,
    ValidationException,
)
from app.models.search import HybridSearchResult, NearestNeighbor, ProductFilters, SearchModality
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.reranker_service import RerankerService
from app.services.vectorstore.search_service import SearchService
from app.services.vectorstore.text_search_service import TextSearchService

logger = get_logger(__name__)


class HybridSearchService:
    """Orchestrates image search, text search, weighted score fusion, and optional reranking."""

    def __init__(
        self,
        *,
        search_service: SearchService | None = None,
        text_search_service: TextSearchService | None = None,
        image_weight: float | None = None,
        text_weight: float | None = None,
        reranker: BaseReranker | None = None,
        reranking_enabled: bool | None = None,
    ) -> None:
        self._search_service = search_service if search_service is not None else SearchService()
        self._text_search_service = (
            text_search_service if text_search_service is not None else TextSearchService()
        )
        self._image_weight = (
            image_weight if image_weight is not None else settings.hybrid_search.image_weight
        )
        self._text_weight = (
            text_weight if text_weight is not None else settings.hybrid_search.text_weight
        )
        #: Cross-encoder reranking (Phase 11) — an optional refinement
        #: step applied only when a text query is available (a
        #: cross-encoder scores query-document *text* pairs, so an
        #: image-only search has nothing to rerank with; see `.search`'s
        #: own docstring). Composing `RerankerService` directly here
        #: (rather than depending only on `BaseReranker`) would be wrong
        #: for testability, so the constructor accepts either.
        self._reranker: BaseReranker = reranker if reranker is not None else RerankerService()
        self._reranking_enabled = (
            reranking_enabled if reranking_enabled is not None else settings.reranker.enabled
        )

    async def search(
        self,
        *,
        image: ProductImage | None = None,
        text: str | None = None,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        reranking_enabled: bool | None = None,
    ) -> list[HybridSearchResult]:
        """Search by `image`, `text`, or both — at least one must be given.

        When reranking is active (`reranking_enabled`, defaulting to this
        instance's own configured value) *and* a text query is present,
        the underlying search(es) are overfetched up to
        `RERANKER__TOP_N` candidates, reranked by cross-encoder against
        `text`, and truncated back down to the requested `top_k` — an
        image-only search has no text to build a query-document pair
        from, so it's returned unreranked regardless of
        `reranking_enabled` (a documented limitation, not a bug).

        Raises `ValidationException` if neither `image` nor `text` is
        provided; otherwise raises whatever `SearchService`/
        `TextSearchService` raise for the modality/modalities actually
        used, `HybridSearchException` if combining their results (hybrid
        mode only) fails unexpectedly, or `RerankException` if reranking
        fails.
        """
        has_text = text is not None and text.strip() != ""

        if image is None and not has_text:
            raise ValidationException("At least one of an image or a text query must be provided.")

        resolved_top_k = top_k if top_k is not None else settings.vector_store.default_top_k
        rerank_active = (
            reranking_enabled if reranking_enabled is not None else self._reranking_enabled
        ) and has_text
        retrieval_top_k = (
            max(settings.reranker.top_n, resolved_top_k) if rerank_active else resolved_top_k
        )

        if image is not None and not has_text:
            logger.info("Hybrid search dispatching: mode=image-only")
            result = await self._search_service.search_by_image(
                image, top_k=resolved_top_k, filters=filters
            )
            return [
                _single_modality_result(neighbor, SearchModality.IMAGE)
                for neighbor in result.neighbors
            ]

        if image is None:
            logger.info("Hybrid search dispatching: mode=text-only")
            assert text is not None  # narrowed by `has_text` above
            result = await self._text_search_service.search_by_text(
                text, top_k=retrieval_top_k, filters=filters
            )
            results = [
                _single_modality_result(neighbor, SearchModality.TEXT)
                for neighbor in result.neighbors
            ]
            return await self._finalize(text, results, resolved_top_k, rerank_active)

        logger.info("Hybrid search dispatching: mode=hybrid")
        assert text is not None  # narrowed by `has_text` above
        image_result = await self._search_service.search_by_image(
            image, top_k=retrieval_top_k, filters=filters
        )
        text_result = await self._text_search_service.search_by_text(
            text, top_k=retrieval_top_k, filters=filters
        )

        try:
            fused = _fuse(
                image_result.neighbors,
                text_result.neighbors,
                image_weight=self._image_weight,
                text_weight=self._text_weight,
            )
        except Exception as exc:
            raise HybridSearchException("Failed to combine image and text search results.") from exc

        fused.sort(key=lambda result: result.score, reverse=True)
        logger.info(
            "Hybrid search completed: image_results=%d, text_results=%d, fused_results=%d",
            len(image_result.neighbors),
            len(text_result.neighbors),
            min(len(fused), resolved_top_k),
        )
        return await self._finalize(text, fused, resolved_top_k, rerank_active)

    async def _finalize(
        self,
        text: str,
        results: list[HybridSearchResult],
        resolved_top_k: int,
        rerank_active: bool,
    ) -> list[HybridSearchResult]:
        """Truncate `results` to `resolved_top_k`, reranking first if `rerank_active`."""
        if not rerank_active:
            return results[:resolved_top_k]

        rerank_result = await self._reranker.rerank(text, results, top_k=resolved_top_k)
        by_id = {result.product_id: result for result in results}
        logger.info(
            "Reranking applied: candidates=%d, reranked=%d",
            len(results),
            len(rerank_result.candidates),
        )
        return [
            by_id[candidate.product_id].model_copy(update={"score": candidate.rerank_score})
            for candidate in rerank_result.candidates
        ]

    async def retrieve_metadata(self, product_id: UUID) -> dict[str, Any] | None:
        """Return `product_id`'s stored metadata payload, or `None` if absent.

        A read-only lookup for callers that need the *subject's* own
        attributes rather than its neighbours -- pricing uses it to learn the
        category it should restrict comparables to. Prefers the image
        collection and falls back to text, since both carry the same payload.
        """
        point = await self._search_service.retrieve_by_id(product_id)
        if point is None:
            point = await self._text_search_service.retrieve_by_id(product_id)
        return point.metadata if point is not None else None

    async def search_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        modality: SearchModality | None = None,
    ) -> list[HybridSearchResult]:
        """Find products similar to an already-indexed product, identified by ID (Phase 9).

        Unlike `.search()` (which embeds a freshly submitted image/text
        query), this reuses `product_id`'s own already-stored embedding(s)
        — no image file or text string needs to be resubmitted.
        `modality` restricts which stored embedding(s) to search from:
        `None` uses both and fuses them the same way `.search()` does;
        `SearchModality.IMAGE`/`SearchModality.TEXT` restrict to just that
        one. `RecommendationEngineService` uses `None` for "similar"
        recommendations and `SearchModality.TEXT` for "related" ones
        (category/attribute-driven, decoupled from pure visual likeness).

        The target product itself is always excluded from the returned
        results. Raises `ResourceNotFoundException` if `product_id` isn't
        indexed in the collection(s) `modality` requires, or
        `HybridSearchException` if fusing (hybrid mode only) fails
        unexpectedly.
        """
        want_image = modality is not SearchModality.TEXT
        want_text = modality is not SearchModality.IMAGE

        image_point = await self._search_service.retrieve_by_id(product_id) if want_image else None
        text_point = (
            await self._text_search_service.retrieve_by_id(product_id) if want_text else None
        )
        if want_image and image_point is None:
            raise ResourceNotFoundException(
                f"Product '{product_id}' is not indexed.", resource="product"
            )
        if want_text and text_point is None:
            raise ResourceNotFoundException(
                f"Product '{product_id}' is not indexed.", resource="product"
            )

        # Requests one extra candidate internally so excluding the target
        # product itself (below) never silently shrinks the caller's
        # requested `top_k`.
        resolved_top_k = top_k if top_k is not None else settings.vector_store.default_top_k
        internal_top_k = resolved_top_k + 1

        if modality is SearchModality.TEXT:
            assert text_point is not None
            result = await self._text_search_service.search_by_vector(
                text_point.vector, top_k=internal_top_k, filters=filters
            )
            results = [
                _single_modality_result(neighbor, SearchModality.TEXT)
                for neighbor in result.neighbors
            ]
        elif modality is SearchModality.IMAGE:
            assert image_point is not None
            result = await self._search_service.search_by_vector(
                image_point.vector, top_k=internal_top_k, filters=filters
            )
            results = [
                _single_modality_result(neighbor, SearchModality.IMAGE)
                for neighbor in result.neighbors
            ]
        else:
            assert image_point is not None
            assert text_point is not None
            image_result = await self._search_service.search_by_vector(
                image_point.vector, top_k=internal_top_k, filters=filters
            )
            text_result = await self._text_search_service.search_by_vector(
                text_point.vector, top_k=internal_top_k, filters=filters
            )
            try:
                results = _fuse(
                    image_result.neighbors,
                    text_result.neighbors,
                    image_weight=self._image_weight,
                    text_weight=self._text_weight,
                )
            except Exception as exc:
                raise HybridSearchException(
                    "Failed to combine image and text search results."
                ) from exc
            results.sort(key=lambda result: result.score, reverse=True)

        results = [result for result in results if result.product_id != product_id]
        logger.info(
            "Hybrid search-by-id completed: product_id=%s, modality=%s, results=%d",
            product_id,
            modality.value if modality is not None else "hybrid",
            min(len(results), resolved_top_k),
        )
        return results[:resolved_top_k]


@dataclass
class _FusionEntry:
    metadata: dict[str, object]
    image_score: float = 0.0
    text_score: float = 0.0
    modalities: set[SearchModality] = field(default_factory=set)


def _fuse(
    image_neighbors: list[NearestNeighbor],
    text_neighbors: list[NearestNeighbor],
    *,
    image_weight: float,
    text_weight: float,
) -> list[HybridSearchResult]:
    """Merge two per-modality result sets into one fused, deduplicated list.

    A `product_id` present in only one input list gets a `0.0` score for
    the modality it's missing from — exactly the "missing modality
    contributes zero" rule the fusion formula requires.
    """
    entries: dict[UUID, _FusionEntry] = {}

    for neighbor in image_neighbors:
        entry = entries.setdefault(neighbor.product_id, _FusionEntry(metadata=neighbor.metadata))
        entry.image_score = neighbor.score
        entry.modalities.add(SearchModality.IMAGE)

    for neighbor in text_neighbors:
        entry = entries.setdefault(neighbor.product_id, _FusionEntry(metadata=neighbor.metadata))
        entry.text_score = neighbor.score
        entry.modalities.add(SearchModality.TEXT)

    return [
        HybridSearchResult(
            product_id=product_id,
            score=image_weight * entry.image_score + text_weight * entry.text_score,
            metadata=entry.metadata,
            matched_modalities=sorted(entry.modalities, key=lambda modality: modality.value),
            image_score=entry.image_score,
            text_score=entry.text_score,
        )
        for product_id, entry in entries.items()
    ]


def _single_modality_result(
    neighbor: NearestNeighbor, modality: SearchModality
) -> HybridSearchResult:
    """Wrap one single-modality `NearestNeighbor` as a `HybridSearchResult`, score untouched."""
    return HybridSearchResult(
        product_id=neighbor.product_id,
        score=neighbor.score,
        metadata=neighbor.metadata,
        matched_modalities=[modality],
        image_score=neighbor.score if modality is SearchModality.IMAGE else 0.0,
        text_score=neighbor.score if modality is SearchModality.TEXT else 0.0,
    )
