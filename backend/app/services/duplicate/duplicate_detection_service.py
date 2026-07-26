"""`DuplicateDetectionService`: the duplicate-detection pipeline orchestrator.

Pipeline, per the phase spec's own diagram:

    HybridSearchService.search (image + text) -> top-K candidates
        -> SimilarityScorer.score (one call per candidate)
        -> rank by overall_similarity, threshold the best one
        -> DuplicateDecision

Deliberately thin, mirroring `CatalogIntelligenceService` (Phase 7) and
`HybridSearchService` (Phase 6): this class does no similarity math of
its own — `SimilarityScorer` owns every signal computation, so the same
scorer can be reused elsewhere (recommendation ranking, cross-encoder
reranking) without dragging retrieval/decision logic along with it, per
the phase's own "why this design" rationale. `detect` holds no mutable
instance state and every call operates on its own local variables, so a
single `DuplicateDetectionService` instance is safe to share across
concurrent requests — the same reasoning already established for
`HybridSearchService`/`CatalogIntelligenceService`.
"""

import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import DuplicateDetectionException
from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_result import DuplicateResult
from app.models.product_attributes import ProductAttributes
from app.schemas.product import ProductImage
from app.services.duplicate.similarity_scorer import SimilarityScorer
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.utils.text import build_text_representation

logger = get_logger(__name__)


class DuplicateDetectionService:
    """Retrieves duplicate candidates via hybrid search, scores, and decides."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        similarity_scorer: SimilarityScorer | None = None,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._similarity_scorer = (
            similarity_scorer if similarity_scorer is not None else SimilarityScorer()
        )
        self._top_k = top_k if top_k is not None else settings.duplicate_detection.top_k
        self._threshold = (
            threshold if threshold is not None else settings.duplicate_detection.threshold
        )

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
        defaults. Raises whatever `HybridSearchService` raises for
        candidate retrieval, or `DuplicateDetectionException` if scoring
        the otherwise successfully-retrieved candidates fails
        unexpectedly.
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k
        resolved_threshold = threshold if threshold is not None else self._threshold

        text = build_text_representation(name, brand, category, description)
        candidates = await self._hybrid_search_service.search(
            image=image, text=text, top_k=resolved_top_k
        )
        logger.info("Duplicate candidate retrieval complete: candidates=%d", len(candidates))

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
