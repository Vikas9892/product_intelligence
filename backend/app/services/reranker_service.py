"""`RerankerService`: the cross-encoder reranking pipeline orchestrator (Phase 11).

Pipeline, per the phase spec's own diagram:

    already-retrieved candidates -> top `RERANK_TOP_N` (pool cap)
        -> build one (query, document) pair per pooled candidate
        -> CrossEncoderService.score_pairs (one batched call)
        -> sigmoid-normalize each raw score into [0, 1]
        -> sort by normalized score, descending
        -> truncate to `top_k`
        -> RerankResult (RerankedCandidate + RerankReason per survivor)

Deliberately thin, mirroring `RecommendationEngineService`/
`DuplicateDetectionService`: this class does no retrieval of its own —
`candidates` must already have been retrieved by
`HybridSearchService`/`HybridSearchService.search_by_product_id` before
reaching here (the phase's own "Do not perform retrieval here"
requirement) — and `CrossEncoderService` owns the actual model
inference, so this class's only job is pooling, pairing, sorting, and
truncating.

**Why sigmoid-normalize?** A cross-encoder outputs an unbounded
relevance logit (a confident match can score well above `1.0`, an
irrelevant pair well below `0.0`) — left as-is, every caller downstream
(`HybridSearchService`/`RecommendationEngineService`/
`DuplicateDetectionService`, Milestone 4) that substitutes a rerank score
into an existing `[0, 1]`-scored field would either lose precision to
clamping (many confidently-relevant candidates collapsing to `1.0`) or
need its own ad-hoc normalization. Normalizing once, here, keeps
`RerankedCandidate.rerank_score` directly comparable to every other score
in this codebase (`HybridSearchResult.score`, `RecommendationCandidate.
similarity_score`, `DuplicateResult.overall_similarity`, ...) without
each caller reinventing the same transform.

**Why pool at `RERANK_TOP_N` before scoring?** Balancing quality and
latency (the phase's own framing) — a cross-encoder is far more
expensive per candidate than the embedding cosine similarity that found
these candidates in the first place, so only the top `RERANK_TOP_N`
(by whatever ordering retrieval already produced) are ever sent through
it, regardless of how many candidates are passed in.
"""

import math
import time

from app.core.config import settings
from app.core.langfuse import observe, update_active_span
from app.core.logging import get_logger
from app.exceptions.errors import RerankException
from app.metrics.metrics_registry import MetricsRegistry
from app.models.rerank_reason import RerankReason
from app.models.rerank_result import RerankResult
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult
from app.services.base_reranker import BaseReranker
from app.services.cross_encoder_service import CrossEncoderService
from app.utils.text import build_text_representation_from_metadata

logger = get_logger(__name__)


class RerankerService(BaseReranker):
    """Reranks already-retrieved candidates against a query using a cross-encoder."""

    def __init__(
        self,
        *,
        cross_encoder_service: CrossEncoderService | None = None,
        top_n: int | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._cross_encoder_service = (
            cross_encoder_service if cross_encoder_service is not None else CrossEncoderService()
        )
        self._top_n = top_n if top_n is not None else settings.reranker.top_n
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    @observe(name="cross_encoder_rerank")
    async def rerank(
        self,
        query: str,
        candidates: list[HybridSearchResult],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        """Rerank `candidates` against `query`, returning at most `top_k` of them.

        Raises `RerankException` if scoring or the reranking pipeline
        itself fails unexpectedly.
        """
        start = time.monotonic()
        pool = candidates[: self._top_n]

        update_active_span(
            metadata={
                "query": query,
                "input_candidates_count": len(candidates),
                "pooled_candidates_count": len(pool),
                "top_k": top_k,
                "top_n_cap": self._top_n,
            }
        )

        if not pool:
            return RerankResult(
                query=query, candidates=[], processing_time=time.monotonic() - start
            )

        try:
            pairs = [(query, _document_text(candidate)) for candidate in pool]
            raw_scores = await self._cross_encoder_service.score_pairs(pairs)
        except RerankException:
            self._metrics.observe_rerank(seconds=time.monotonic() - start, success=False)
            raise
        except Exception as exc:
            self._metrics.observe_rerank(seconds=time.monotonic() - start, success=False)
            raise RerankException("Failed to rerank candidates.") from exc

        original_ranks = {
            candidate.product_id: rank for rank, candidate in enumerate(pool, start=1)
        }
        scored = sorted(zip(pool, raw_scores, strict=True), key=lambda pair: pair[1], reverse=True)
        resolved_top_k = top_k if top_k is not None else len(scored)
        final = scored[:resolved_top_k]

        reranked = [
            _to_reranked_candidate(
                candidate,
                raw_score,
                original_rank=original_ranks[candidate.product_id],
                final_rank=final_rank,
            )
            for final_rank, (candidate, raw_score) in enumerate(final, start=1)
        ]

        processing_time = time.monotonic() - start
        self._metrics.observe_rerank(seconds=processing_time, success=True)
        logger.info(
            "Reranking complete: candidates=%d, pool=%d, reranked=%d, duration=%.4fs",
            len(candidates),
            len(pool),
            len(reranked),
            processing_time,
        )
        return RerankResult(
            query=query,
            candidates=reranked,
            processing_time=processing_time,
            original_count=len(pool),
        )


def _document_text(candidate: HybridSearchResult) -> str:
    """Build the cross-encoder's "document" side of the pair from a candidate's own metadata.

    Falls back to the candidate's `product_id` when its metadata yields no
    usable text (missing/malformed `name`/`brand`/`category`/`description`)
    — a cross-encoder still needs *some* non-empty string, and a
    candidate with unusable metadata shouldn't crash the whole rerank
    pass over it.
    """
    text = build_text_representation_from_metadata(candidate.metadata)
    return text if text else str(candidate.product_id)


def _to_reranked_candidate(
    candidate: HybridSearchResult, raw_score: float, *, original_rank: int, final_rank: int
) -> RerankedCandidate:
    rank_delta = original_rank - final_rank
    return RerankedCandidate(
        product_id=candidate.product_id,
        original_score=candidate.score,
        rerank_score=_normalize(raw_score),
        final_rank=final_rank,
        metadata=candidate.metadata,
        reason=RerankReason(
            original_rank=original_rank,
            final_rank=final_rank,
            rank_delta=rank_delta,
            explanation=_explanation(original_rank, final_rank),
        ),
    )


def _normalize(raw_score: float) -> float:
    """Sigmoid-normalize an unbounded cross-encoder logit into `(0, 1)` — see module docstring."""
    return 1.0 / (1.0 + math.exp(-raw_score))


def _explanation(original_rank: int, final_rank: int) -> str:
    if final_rank < original_rank:
        return (
            f"Moved up from position {original_rank} to {final_rank} after cross-encoder reranking."
        )
    if final_rank > original_rank:
        return f"Moved down from position {original_rank} to {final_rank} after cross-encoder reranking."
    return f"Kept at position {final_rank} after cross-encoder reranking."
