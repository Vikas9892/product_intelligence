"""`DuplicateVerificationService`: the cross-encoder + business-rules verification pipeline (Phase 15).

The production-grade successor to weighted-similarity duplicate detection
(Phase 8), following the pattern of many real search/ranking systems:

    hybrid retrieval (top-K) -> cross-encoder reranking -> business-rule
    validation -> explainable duplicate confidence

Built *on top of* the existing Phase 11 reranking infrastructure rather
than duplicating it: it composes `HybridSearchService` (retrieval) and
`RerankerService` (the cross-encoder), and (Milestone 4) a
`BusinessRulesEvaluator` — it never reimplements retrieval or reranking.
Distinct from `DuplicateDetectionService` (Phase 8, unchanged): that
service produces a single *weighted* `DuplicateDecision` and still powers
upload-time WARN/BLOCK; this one produces an *explainable*
`DuplicateVerification` that separates the cross-encoder signal from the
raw retrieval signal and lists human-readable reasons, for the richer
`POST /products/check-duplicate` response.

**Milestone 3 (this commit) — reranking pipeline only.** `verify` runs
retrieval, then reranking, and reports `cross_encoder_score` /
`retrieval_similarity` / a threshold-based `is_duplicate`, with
`confidence` equal to the cross-encoder score. The business-rule
combination (brand/category/price/attribute signals adjusting the
confidence and adding reasons) arrives in Milestone 4 — hence the single
"cross-encoder relevance" reason for now.

Holds no mutable per-request state (every call works on locals), so one
instance is safe to share across concurrent requests — the same reasoning
`DuplicateDetectionService`/`HybridSearchService` already document.
"""

import time

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import DuplicateVerificationException, RerankException
from app.metrics.metrics_registry import MetricsRegistry
from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_verification import DuplicateVerification
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult
from app.models.verification_reason import VerificationReason
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.reranker_service import RerankerService
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.utils.text import build_text_representation

logger = get_logger(__name__)


class DuplicateVerificationService:
    """Retrieves candidates, reranks them with a cross-encoder, and reports duplicate confidence."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        reranker: BaseReranker | None = None,
        top_k: int | None = None,
        cross_encoder_threshold: float | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._reranker: BaseReranker = reranker if reranker is not None else RerankerService()
        self._top_k = top_k if top_k is not None else settings.duplicate_detection.top_k
        self._cross_encoder_threshold = (
            cross_encoder_threshold
            if cross_encoder_threshold is not None
            else settings.duplicate_verification.cross_encoder_threshold
        )
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    async def verify(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
        image: ProductImage,
        top_k: int | None = None,
    ) -> DuplicateVerification:
        """Retrieve, rerank, and report whether the described product is a likely duplicate.

        `image` must describe a file already written under the upload
        directory (the same contract `DuplicateDetectionService.detect`
        has). Uses the *raw* submitted name/brand/category/description to
        build the retrieval and cross-encoder query text, exactly as
        `DuplicateDetectionService` does. Raises
        `DuplicateVerificationException` if reranking the otherwise
        successfully-retrieved candidates fails unexpectedly (an actual
        `RerankException` propagates as itself).
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k
        text = build_text_representation(name, brand, category, description)

        # Retrieve with reranking off — this service runs its own explicit
        # rerank pass below, so letting HybridSearchService also rerank
        # internally would score the same candidates by the cross-encoder
        # twice (the same reasoning `DuplicateDetectionService` documents).
        candidates = await self._hybrid_search_service.search(
            image=image, text=text, top_k=resolved_top_k, reranking_enabled=False
        )
        logger.info("Verification candidate retrieval complete: candidates=%d", len(candidates))

        if not candidates:
            return DuplicateVerification(
                is_duplicate=False,
                confidence=0.0,
                reasons=[
                    VerificationReason(
                        code="no_candidates",
                        message="No existing products were found to compare against.",
                    )
                ],
            )

        try:
            rerank_result = await self._reranker.rerank(text, candidates, top_k=resolved_top_k)
        except RerankException:
            # A reranking failure is already a well-defined 500
            # (`RerankException`) — let it propagate as itself rather than
            # reclassifying it, the same way `HybridSearchService`/
            # `DuplicateDetectionService` let their reranker's exception
            # through.
            raise
        except Exception as exc:
            raise DuplicateVerificationException(
                "Failed to rerank candidates for duplicate verification."
            ) from exc

        by_id = {candidate.product_id: candidate for candidate in candidates}
        best = rerank_result.candidates[0]
        cross_encoder_score = best.rerank_score
        retrieval_similarity = best.original_score
        is_duplicate = cross_encoder_score >= self._cross_encoder_threshold

        verification = DuplicateVerification(
            is_duplicate=is_duplicate,
            confidence=cross_encoder_score,
            cross_encoder_score=cross_encoder_score,
            retrieval_similarity=retrieval_similarity,
            matched_product=best.product_id,
            reasons=[
                VerificationReason(
                    code="cross_encoder",
                    message=(
                        f"Cross-encoder relevance {cross_encoder_score:.2f} "
                        f"{'meets' if is_duplicate else 'is below'} the "
                        f"{self._cross_encoder_threshold:.2f} threshold."
                    ),
                )
            ],
            top_candidates=[
                _to_candidate(reranked, by_id.get(reranked.product_id))
                for reranked in rerank_result.candidates
            ],
        )

        logger.info(
            "Duplicate verification complete: is_duplicate=%s, cross_encoder_score=%.2f, "
            "candidates=%d, processing_time=%.4fs",
            verification.is_duplicate,
            cross_encoder_score,
            len(rerank_result.candidates),
            time.monotonic() - start,
        )
        return verification


def _clamp01(value: float) -> float:
    """Clamp a raw similarity into `[0, 1]` for `DuplicateCandidate`'s constrained fields."""
    return max(0.0, min(1.0, value))


def _to_candidate(
    reranked: RerankedCandidate, original: HybridSearchResult | None
) -> DuplicateCandidate:
    """Flatten a reranked candidate (plus its original per-modality retrieval scores) into a `DuplicateCandidate`.

    `overall_similarity` is the cross-encoder rerank score (the signal
    verification actually ranks on); `image`/`text` come from the original
    `HybridSearchResult`'s per-modality retrieval scores when available.
    `metadata`/`attribute` similarities are `0.0` here — those are
    `SimilarityScorer`'s weighted signals, which the verification pipeline
    doesn't compute (it uses business rules instead, Milestone 4).
    """
    return DuplicateCandidate(
        product_id=reranked.product_id,
        image_similarity=_clamp01(original.image_score if original is not None else 0.0),
        text_similarity=_clamp01(original.text_score if original is not None else 0.0),
        metadata_similarity=0.0,
        attribute_similarity=0.0,
        overall_similarity=_clamp01(reranked.rerank_score),
    )
