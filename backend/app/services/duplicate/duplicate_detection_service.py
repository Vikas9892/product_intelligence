"""`DuplicateDetectionService`: the duplicate-detection pipeline orchestrator.

Pipeline, per the phase spec's own diagram:

    HybridSearchService.search (image + text) -> top-K candidates
        -> SimilarityScorer.score (one call per candidate)
        -> rank by overall_similarity, threshold the best one
        -> DuplicateDecision

Deliberately thin, mirroring `CatalogIntelligenceService` (Phase 7) and
`HybridSearchService` (Phase 6): this class does no similarity math of
its own — `SimilarityScorer` owns every signal computation, so the same
scorer can be reused elsewhere (recommendation ranking) without dragging
retrieval/decision logic along with it, per the phase's own "why this
design" rationale. `detect` holds no mutable instance state and every
call operates on its own local variables, so a single
`DuplicateDetectionService` instance is safe to share across concurrent
requests — the same reasoning already established for
`HybridSearchService`/`CatalogIntelligenceService`.

**Cross-encoder reranking (Phase 11, optional).** When enabled, the
overfetched candidate pool is reranked against the checked product's own
text (the same `text` `detect`/`detect_by_product_id` already build for
hybrid search) *before* `SimilarityScorer` sees it. Unlike
`RecommendationEngineService` (which substitutes the rerank score into
`candidate.score`, the exact signal `RecommendationScorer` reuses),
`SimilarityScorer` never reads `candidate.score` — it reads
`candidate.text_score` directly — so reranking here replaces
`text_score` instead: a cross-encoder's joint-attention relevance
judgment is a strictly more accurate refinement of "how textually
similar is this candidate" than the embedding cosine similarity
`text_score` started as, and substituting it flows straight into the
existing `text_weight`-weighted formula with no changes to
`SimilarityScorer` itself.
"""

import time
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import DuplicateDetectionException, ResourceNotFoundException
from app.metrics.metrics_registry import MetricsRegistry
from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_result import DuplicateResult
from app.models.product_attributes import ProductAttributes
from app.models.search import HybridSearchResult
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.duplicate.similarity_scorer import SimilarityScorer
from app.services.reranker_service import RerankerService
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.utils.text import build_text_representation, build_text_representation_from_metadata

logger = get_logger(__name__)


class DuplicateDetectionService:
    """Retrieves duplicate candidates via hybrid search, scores, and decides."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        vector_store: BaseVectorStore | None = None,
        similarity_scorer: SimilarityScorer | None = None,
        reranker: BaseReranker | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        #: Only used by `detect_by_product_id` (Phase 10), to fetch an
        #: already-indexed target's own metadata — `detect()` itself never
        #: touches the vector store directly, it only searches via
        #: `HybridSearchService`. Composed the same way
        #: `RecommendationEngineService` composes its own `BaseVectorStore`,
        #: for the same reason: a direct-lookup need independent of
        #: `HybridSearchService`'s own (private) vector store access.
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._similarity_scorer = (
            similarity_scorer if similarity_scorer is not None else SimilarityScorer()
        )
        self._reranker: BaseReranker = reranker if reranker is not None else RerankerService()
        self._top_k = top_k if top_k is not None else settings.duplicate_detection.top_k
        self._threshold = (
            threshold if threshold is not None else settings.duplicate_detection.threshold
        )
        self._reranking_enabled = (
            reranking_enabled if reranking_enabled is not None else settings.reranker.enabled
        )
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    async def detect(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        attributes: ProductAttributes,
        image: ProductImage,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        """Check whether a product (not yet indexed) is likely a duplicate of an existing one.

        Uses the *raw* submitted name/brand/category/description (via
        `build_text_representation`) to build the hybrid search's text
        query — the same natural-language reasoning `ProductService`
        already applies to text embedding and catalog intelligence, not
        the normalized/slugified fields. `top_k`/`threshold` override this
        instance's configured defaults for this call only — used by
        `POST /products/check-duplicate` (Milestone 5), which lets a
        caller tune both per-request; `ProductService`'s own upload
        integration never passes them, relying on the configured
        defaults. When reranking is active (`reranking_enabled`,
        defaulting to this instance's own configured value), candidates
        are reranked against `text` before scoring — see the module
        docstring for why that replaces `text_score`, not `score`. Raises
        whatever `HybridSearchService` raises for candidate retrieval, or
        `DuplicateDetectionException` if scoring the otherwise
        successfully-retrieved candidates fails unexpectedly.
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k
        resolved_threshold = threshold if threshold is not None else self._threshold
        rerank_active = (
            reranking_enabled if reranking_enabled is not None else self._reranking_enabled
        )
        retrieval_top_k = (
            max(settings.reranker.top_n, resolved_top_k) if rerank_active else resolved_top_k
        )

        text = build_text_representation(name, brand, category, description)
        # `reranking_enabled=False`: this class applies its own rerank
        # pass below (substituting into `text_score`, not `score`) — if
        # `HybridSearchService.search` also reranked internally, the same
        # candidates would be scored by the cross-encoder twice.
        candidates = await self._hybrid_search_service.search(
            image=image, text=text, top_k=retrieval_top_k, reranking_enabled=False
        )
        logger.info("Duplicate candidate retrieval complete: candidates=%d", len(candidates))

        if rerank_active and candidates:
            candidates = await _rerank_candidates(
                self._reranker, text, candidates, top_k=resolved_top_k
            )
            logger.info("Reranking applied: candidates=%d", len(candidates))

        try:
            results = [
                self._similarity_scorer.score(
                    name=name,
                    brand=brand,
                    category=category,
                    attributes=attributes,
                    candidate=candidate,
                )
                for candidate in candidates
            ]
            decision = _build_decision(results, threshold=resolved_threshold)
        except Exception as exc:
            raise DuplicateDetectionException(
                "Failed to score candidates for duplicate detection."
            ) from exc

        self._metrics.record_duplicate_detection(
            similarity_scores=[result.overall_similarity for result in results]
        )
        processing_time = time.monotonic() - start
        logger.info(
            "Duplicate detection complete: is_duplicate=%s, confidence=%.2f, "
            "candidates=%d, processing_time=%.4fs",
            decision.is_duplicate,
            decision.confidence,
            len(candidates),
            processing_time,
        )
        return decision

    async def detect_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        """Check whether an *already-indexed* product looks like a duplicate of another.

        Mirrors `detect()`, but the target is an already-uploaded product
        identified only by ID — its own stored metadata (name/brand/
        category/color/material/gender/style) is fetched directly and
        candidates come from `HybridSearchService.search_by_product_id`
        (Phase 9, which also excludes the target itself), rather than a
        freshly submitted image/text. Reuses the exact same
        `SimilarityScorer`/`_build_decision` logic `detect()` uses — no
        second, parallel scoring implementation — so `RetrievalEvaluator`
        (Phase 10) can benchmark duplicate detection against already-
        uploaded products without needing their original files again.

        Raises `ResourceNotFoundException` if `product_id` isn't indexed,
        or `DuplicateDetectionException` if scoring fails unexpectedly.
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k
        resolved_threshold = threshold if threshold is not None else self._threshold
        rerank_active = (
            reranking_enabled if reranking_enabled is not None else self._reranking_enabled
        )
        retrieval_top_k = (
            max(settings.reranker.top_n, resolved_top_k) if rerank_active else resolved_top_k
        )

        target_point = await self._vector_store.retrieve_text(product_id)
        if target_point is None:
            target_point = await self._vector_store.retrieve_image(product_id)
        if target_point is None:
            raise ResourceNotFoundException(
                f"Product '{product_id}' was not found.", resource="product"
            )

        metadata = target_point.metadata
        name = metadata.get("name") or ""
        brand = metadata.get("brand")
        category = metadata.get("category")
        attributes = ProductAttributes(
            brand=brand if isinstance(brand, str) else None,
            category=category if isinstance(category, str) else None,
            color=metadata.get("color") if isinstance(metadata.get("color"), str) else None,
            material=(
                metadata.get("material") if isinstance(metadata.get("material"), str) else None
            ),
            gender=metadata.get("gender") if isinstance(metadata.get("gender"), str) else None,
            style=metadata.get("style") if isinstance(metadata.get("style"), str) else None,
        )

        candidates = await self._hybrid_search_service.search_by_product_id(
            product_id, top_k=retrieval_top_k
        )
        logger.info(
            "Duplicate candidate retrieval (by ID) complete: product_id=%s, candidates=%d",
            product_id,
            len(candidates),
        )

        if rerank_active and candidates:
            query_text = build_text_representation_from_metadata(metadata)
            candidates = await _rerank_candidates(
                self._reranker, query_text, candidates, top_k=resolved_top_k
            )
            logger.info(
                "Reranking applied: product_id=%s, candidates=%d", product_id, len(candidates)
            )

        try:
            results = [
                self._similarity_scorer.score(
                    name=str(name),
                    brand=brand if isinstance(brand, str) else None,
                    category=category if isinstance(category, str) else None,
                    attributes=attributes,
                    candidate=candidate,
                )
                for candidate in candidates
            ]
            decision = _build_decision(results, threshold=resolved_threshold)
        except Exception as exc:
            raise DuplicateDetectionException(
                "Failed to score candidates for duplicate detection."
            ) from exc

        self._metrics.record_duplicate_detection(
            similarity_scores=[result.overall_similarity for result in results]
        )
        processing_time = time.monotonic() - start
        logger.info(
            "Duplicate detection (by ID) complete: product_id=%s, is_duplicate=%s, "
            "confidence=%.2f, candidates=%d, processing_time=%.4fs",
            product_id,
            decision.is_duplicate,
            decision.confidence,
            len(candidates),
            processing_time,
        )
        return decision


async def _rerank_candidates(
    reranker: BaseReranker,
    query: str,
    candidates: list[HybridSearchResult],
    *,
    top_k: int,
) -> list[HybridSearchResult]:
    """Rerank `candidates` against `query`, substituting each survivor's `text_score`
    with its cross-encoder-refined rerank score — see the module docstring for why
    `text_score` (not `score`) is the field `SimilarityScorer` actually reads."""
    rerank_result = await reranker.rerank(query, candidates, top_k=top_k)
    by_id = {candidate.product_id: candidate for candidate in candidates}
    return [
        by_id[reranked.product_id].model_copy(update={"text_score": reranked.rerank_score})
        for reranked in rerank_result.candidates
    ]


def _build_decision(results: list[DuplicateResult], *, threshold: float) -> DuplicateDecision:
    """Rank scored candidates and decide, based on the best one's `overall_similarity`."""
    if not results:
        return DuplicateDecision(
            is_duplicate=False,
            confidence=0.0,
            reason="No candidates were found to compare against.",
        )

    ranked = sorted(results, key=lambda result: result.overall_similarity, reverse=True)
    best = ranked[0]
    top_candidates = [_to_candidate(result) for result in ranked]

    if best.overall_similarity >= threshold:
        return DuplicateDecision(
            is_duplicate=True,
            confidence=best.overall_similarity,
            reason=(
                f"Overall similarity {best.overall_similarity:.2f} meets or exceeds "
                f"the {threshold:.2f} threshold."
            ),
            matched_product=best.product_id,
            top_candidates=top_candidates,
        )

    return DuplicateDecision(
        is_duplicate=False,
        confidence=best.overall_similarity,
        reason=(
            f"Best candidate similarity {best.overall_similarity:.2f} is below "
            f"the {threshold:.2f} threshold."
        ),
        top_candidates=top_candidates,
    )


def _to_candidate(result: DuplicateResult) -> DuplicateCandidate:
    """Flatten a `DuplicateResult`'s `SimilaritySignal` list into a `DuplicateCandidate`."""
    by_name: dict[str, Any] = {signal.name: signal.score for signal in result.signals}
    return DuplicateCandidate(
        product_id=result.product_id,
        image_similarity=by_name.get("image", 0.0),
        text_similarity=by_name.get("text", 0.0),
        metadata_similarity=by_name.get("metadata", 0.0),
        attribute_similarity=by_name.get("attribute", 0.0),
        overall_similarity=result.overall_similarity,
    )
