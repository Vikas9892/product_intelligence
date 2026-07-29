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
from app.models.product_attributes import ProductAttributes
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult
from app.models.verification_reason import VerificationReason
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.duplicate.business_rules_evaluator import BusinessRulesEvaluator
from app.services.reranker_service import RerankerService
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.utils.text import build_text_representation

logger = get_logger(__name__)


class DuplicateVerificationService:
    """Retrieves, reranks (cross-encoder), validates (business rules), and reports duplicate confidence."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        reranker: BaseReranker | None = None,
        business_rules_evaluator: BusinessRulesEvaluator | None = None,
        top_k: int | None = None,
        cross_encoder_threshold: float | None = None,
        cross_encoder_weight: float | None = None,
        business_rules_weight: float | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        verification = settings.duplicate_verification
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._reranker: BaseReranker = reranker if reranker is not None else RerankerService()
        self._business_rules_evaluator = (
            business_rules_evaluator
            if business_rules_evaluator is not None
            else BusinessRulesEvaluator()
        )
        self._top_k = top_k if top_k is not None else settings.duplicate_detection.top_k
        self._cross_encoder_threshold = (
            cross_encoder_threshold
            if cross_encoder_threshold is not None
            else verification.cross_encoder_threshold
        )
        self._cross_encoder_weight = (
            cross_encoder_weight
            if cross_encoder_weight is not None
            else verification.cross_encoder_weight
        )
        self._business_rules_weight = (
            business_rules_weight
            if business_rules_weight is not None
            else verification.business_rules_weight
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
        price: float | None = None,
        attributes: ProductAttributes | None = None,
        top_k: int | None = None,
    ) -> DuplicateVerification:
        """Retrieve, rerank, validate, and report whether the described product is a likely duplicate.

        `image` must describe a file already written under the upload
        directory (the same contract `DuplicateDetectionService.detect`
        has). Uses the *raw* submitted name/brand/category/description to
        build the retrieval and cross-encoder query text, exactly as
        `DuplicateDetectionService` does. `price`/`attributes` feed the
        business-rule validation of the best candidate. The final
        `confidence` blends the cross-encoder score and the business-rule
        score by the configured weights; `is_duplicate` requires the
        cross-encoder score to clear its threshold *and* no configured
        hard gate (`require_same_brand`/`require_same_category`) to be
        vetoed. Raises `DuplicateVerificationException` if reranking the
        otherwise successfully-retrieved candidates fails unexpectedly (an
        actual `RerankException` propagates as itself).
        """
        start = time.monotonic()
        resolved_top_k = top_k if top_k is not None else self._top_k
        resolved_attributes = attributes if attributes is not None else ProductAttributes()
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
            self._metrics.record_duplicate_verification(confidence=None, is_duplicate=False)
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

        business_result = self._business_rules_evaluator.evaluate(
            name=name,
            brand=brand,
            category=category,
            price=price,
            attributes=resolved_attributes,
            candidate_metadata=best.metadata,
        )

        confidence = (
            self._cross_encoder_weight * cross_encoder_score
            + self._business_rules_weight * business_result.score
        )
        # A configured hard gate (brand/category mismatch) vetoes the
        # verdict outright, no matter how confident the cross-encoder is —
        # the phase's own "if cross_encoder > 0.95 AND brand same AND
        # category same" rule made absolute.
        is_duplicate = (
            cross_encoder_score >= self._cross_encoder_threshold and not business_result.veto
        )

        verification = DuplicateVerification(
            is_duplicate=is_duplicate,
            confidence=confidence,
            cross_encoder_score=cross_encoder_score,
            retrieval_similarity=retrieval_similarity,
            matched_product=best.product_id,
            reasons=[
                VerificationReason(
                    code="cross_encoder",
                    message=(
                        f"Cross-encoder relevance {cross_encoder_score:.2f} "
                        f"{'meets' if cross_encoder_score >= self._cross_encoder_threshold else 'is below'} "
                        f"the {self._cross_encoder_threshold:.2f} threshold."
                    ),
                ),
                *business_result.reasons,
            ],
            top_candidates=[
                _to_candidate(reranked, by_id.get(reranked.product_id))
                for reranked in rerank_result.candidates
            ],
        )

        self._metrics.record_duplicate_verification(
            confidence=cross_encoder_score, is_duplicate=is_duplicate
        )
        logger.info(
            "Duplicate verification complete: is_duplicate=%s, confidence=%.2f, "
            "cross_encoder_score=%.2f, business_score=%.2f, veto=%s, candidates=%d, "
            "processing_time=%.4fs",
            verification.is_duplicate,
            confidence,
            cross_encoder_score,
            business_result.score,
            business_result.veto,
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
