"""`RecommendationEngineService`: the recommendation pipeline orchestrator (Phase 9).

Pipeline, per the phase spec's own diagram:

    target product_id -> HybridSearchService.search_by_product_id
        (retrieves candidates, self already excluded)
        -> RecommendationScorer.score (one call per candidate)
        -> sort by final_score, descending
        -> diversity filter (round-robin by brand)
        -> top_k

Deliberately thin, mirroring `DuplicateDetectionService`/
`CatalogIntelligenceService`: this class does no similarity/attribute/tag
math of its own — `RecommendationScorer` owns every signal computation,
so the same scorer can be reused elsewhere (a future cross-encoder
reranker, Phase 10) without dragging retrieval/ranking/diversity logic
along with it.

**Why does this class hold its own `BaseVectorStore`, when
`HybridSearchService` already composes one indirectly (via
`SearchService`/`TextSearchService`)?** Those are private to
`HybridSearchService` — reaching into `hybrid_search_service._search_service`
from outside would break encapsulation. Fetching the target product's own
metadata (needed for `RecommendationScorer`'s attribute/tag/quality
signals) is a direct lookup this class needs independently of hybrid
search's own retrieval, so it composes `BaseVectorStore` directly, the
same way `ProductService` does for its own reasons.

**`SIMILAR` vs `RELATED`:** both use the exact same scoring formula —
the phase spec describes one formula, not two. What differs is which
stored embedding(s) anchor candidate retrieval: `SIMILAR` uses the full
hybrid (image + text) profile, `RELATED` uses text/category alone
(`SearchModality.TEXT`), decoupling the result from pure visual likeness
— e.g. a shirt's "related" results lean on category/attributes rather
than which photo looks most alike. `COMPLEMENTARY` is not implemented
(see `RecommendationType`'s own docstring).

**Diversity.** Candidates are overfetched (`_DIVERSITY_OVERFETCH_MULTIPLIER`
times the requested `top_k`) specifically so the diversity filter has
enough variety to work with — asking hybrid search for exactly `top_k`
candidates and then diversifying would have nothing to diversify *from*.
`_diversify` groups already-score-sorted candidates by brand and takes
one candidate per brand per round (best-scoring first), round-robining
across brands until `top_k` is filled — the same product catalog that
would naively return five Nike results in a row instead surfaces Nike,
Adidas, Puma, Asics, then a second Nike, matching the phase's own worked
example.
"""

import time
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import RecommendationException, ResourceNotFoundException
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType
from app.models.search import HybridSearchResult, SearchModality
from app.services.recommendation.recommendation_scorer import RecommendationScorer
from app.services.vectorstore.base import BaseVectorStore
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

#: How many extra candidates to overfetch beyond the requested `top_k` so
#: the diversity filter has enough variety to work with — see module
#: docstring.
_DIVERSITY_OVERFETCH_MULTIPLIER = 3

_ScoredPair = tuple[HybridSearchResult, RecommendationCandidate]


class RecommendationEngineService:
    """Retrieves recommendation candidates for an already-indexed product, scores, ranks, diversifies."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        vector_store: BaseVectorStore | None = None,
        recommendation_scorer: RecommendationScorer | None = None,
        top_k: int | None = None,
        diversity_enabled: bool | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._vector_store = vector_store if vector_store is not None else QdrantVectorStore()
        self._recommendation_scorer = (
            recommendation_scorer if recommendation_scorer is not None else RecommendationScorer()
        )
        self._top_k = top_k if top_k is not None else settings.recommendation.top_k
        self._diversity_enabled = (
            diversity_enabled
            if diversity_enabled is not None
            else settings.recommendation.diversity_enabled
        )

    async def recommend(
        self,
        *,
        product_id: UUID,
        recommendation_type: RecommendationType = RecommendationType.SIMILAR,
        top_k: int | None = None,
    ) -> RecommendationResult:
        """Generate ranked recommendations for the already-indexed product `product_id`.

        Raises `ResourceNotFoundException` if `product_id` isn't indexed,
        whatever `HybridSearchService` raises for candidate retrieval, or
        `RecommendationException` if scoring/ranking the otherwise
        successfully-retrieved candidates fails unexpectedly.
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k

        target_metadata = await self._target_metadata(product_id)

        modality = (
            None if recommendation_type is RecommendationType.SIMILAR else SearchModality.TEXT
        )
        overfetch_top_k = (
            resolved_top_k * _DIVERSITY_OVERFETCH_MULTIPLIER
            if self._diversity_enabled
            else resolved_top_k
        )
        candidates = await self._hybrid_search_service.search_by_product_id(
            product_id, top_k=overfetch_top_k, modality=modality
        )
        logger.info(
            "Recommendation candidate retrieval complete: product_id=%s, candidates=%d",
            product_id,
            len(candidates),
        )

        try:
            scored_pairs: list[_ScoredPair] = [
                (
                    candidate,
                    self._recommendation_scorer.score(
                        target_metadata=target_metadata, candidate=candidate
                    ),
                )
                for candidate in candidates
            ]
            scored_pairs.sort(key=lambda pair: pair[1].final_score, reverse=True)

            if self._diversity_enabled:
                scored_pairs = _diversify(scored_pairs, top_k=resolved_top_k)
                logger.info(
                    "Diversity filtering applied: product_id=%s, retained=%d",
                    product_id,
                    len(scored_pairs),
                )
            else:
                scored_pairs = scored_pairs[:resolved_top_k]

            recommendations = [candidate for _, candidate in scored_pairs]
        except Exception as exc:
            raise RecommendationException(
                "Failed to score or rank recommendation candidates."
            ) from exc

        processing_time = time.monotonic() - start
        logger.info(
            "Recommendations generated: product_id=%s, type=%s, count=%d, processing_time=%.4fs",
            product_id,
            recommendation_type.value,
            len(recommendations),
            processing_time,
        )
        return RecommendationResult(
            recommendations=recommendations,
            processing_time=processing_time,
            recommendation_type=recommendation_type,
        )

    async def _target_metadata(self, product_id: UUID) -> dict[str, Any]:
        """Fetch `product_id`'s own stored metadata — identical in both collections (see `ProductService`)."""
        point = await self._vector_store.retrieve_text(product_id)
        if point is None:
            point = await self._vector_store.retrieve_image(product_id)
        if point is None:
            raise ResourceNotFoundException(
                f"Product '{product_id}' was not found.", resource="product"
            )
        return point.metadata


def _diversify(scored_pairs: list[_ScoredPair], *, top_k: int) -> list[_ScoredPair]:
    """Round-robin `scored_pairs` (already sorted by descending `final_score`) across brands.

    Groups by the candidate's own `brand` metadata (a missing/blank brand
    is its own group, `"_unknown"`) in first-seen order — which, since
    the input is score-sorted, is also best-score-first order across
    brands. Takes one candidate per brand per round until `top_k` is
    filled, so a catalog dominated by one brand still surfaces other
    brands before repeating.
    """
    by_brand: dict[str, list[_ScoredPair]] = {}
    brand_order: list[str] = []
    for pair in scored_pairs:
        hybrid_result, _ = pair
        brand = hybrid_result.metadata.get("brand")
        key = brand if isinstance(brand, str) and brand.strip() else "_unknown"
        if key not in by_brand:
            by_brand[key] = []
            brand_order.append(key)
        by_brand[key].append(pair)

    diversified: list[_ScoredPair] = []
    round_index = 0
    while len(diversified) < top_k:
        added_this_round = False
        for brand in brand_order:
            bucket = by_brand[brand]
            if round_index < len(bucket):
                diversified.append(bucket[round_index])
                added_this_round = True
                if len(diversified) == top_k:
                    break
        if not added_this_round:
            break
        round_index += 1

    return diversified
