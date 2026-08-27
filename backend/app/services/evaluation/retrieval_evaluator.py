"""`RetrievalEvaluator`: runs an evaluation dataset against the existing retrieval
systems and computes standard information-retrieval metrics against each
query's ground truth.

Pipeline, per the phase spec's own diagram:

    EvaluationQuery (RETRIEVAL/RECOMMENDATION/DUPLICATE)
        -> dispatch to HybridSearchService / RecommendationEngineService /
           DuplicateDetectionService, by task_type — no new retrieval
           logic of its own, reusing exactly the same services every
           earlier phase already built and tested
        -> Precision@K / Recall@K / MRR / NDCG@K / Hit Rate / latency
        -> aggregated per task_type into a BenchmarkReport

Deliberately thin, mirroring `RecommendationEngineService`/
`DuplicateDetectionService`: this class computes metrics (pure functions
of "what was retrieved" vs. "what was expected"), never similarity scores
— those come entirely from the systems being evaluated.

**Per-query failure isolation.** One query's failure (a bad `product_id`
in the dataset, an evaluated system raising) is caught and recorded on
that query's own `EvaluationQueryResult.error` rather than aborting the
whole run — a 500-entry benchmark dataset shouldn't fail entirely because
entry #37 references a product that was since deleted. `evaluate` itself
only raises `EvaluationException` for failures outside any single query
(the default dataset failing to load, or aggregation itself failing).

**Image-query evaluation** (`EvaluationQuery.image_path`) is accepted by
the domain model (future-ready, per the phase spec) but not dispatched
here yet — a `RETRIEVAL` query without `text` fails as its own per-query
error, not a crash, the same as any other unsupported/malformed entry.
"""

import math
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.core.langfuse import observe, record_trace_score, update_active_span
from app.core.logging import get_logger
from app.exceptions.errors import EvaluationException, ResourceNotFoundException
from app.models.benchmark_report import BenchmarkReport
from app.models.evaluation_query import EvaluationQuery, EvaluationTaskType
from app.models.evaluation_result import EvaluationQueryResult
from app.models.model_info import ModelInfo
from app.models.model_type import ModelType
from app.models.recommendation_type import RecommendationType
from app.models.rerank_comparison_report import RerankComparisonReport
from app.models.retrieval_metrics import RetrievalMetrics
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.model_registry import ModelRegistry
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.vectorstore.hybrid_search_service import HybridSearchService

logger = get_logger(__name__)

#: Precision@K/Recall@K/NDCG@K/Hit-Rate@K cutoffs, per the phase spec's
#: own "Support configurable K = 1, 5, 10."
DEFAULT_K_VALUES: tuple[int, ...] = (1, 5, 10)


class RetrievalEvaluator:
    """Evaluates hybrid search, duplicate detection, and recommendations against a labeled dataset."""

    def __init__(
        self,
        *,
        hybrid_search_service: HybridSearchService | None = None,
        duplicate_detection_service: DuplicateDetectionService | None = None,
        recommendation_engine_service: RecommendationEngineService | None = None,
        dataset_loader: DatasetLoader | None = None,
        k_values: tuple[int, ...] | None = None,
        latency_metrics_enabled: bool | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._hybrid_search_service = (
            hybrid_search_service if hybrid_search_service is not None else HybridSearchService()
        )
        self._duplicate_detection_service = (
            duplicate_detection_service
            if duplicate_detection_service is not None
            else DuplicateDetectionService()
        )
        self._recommendation_engine_service = (
            recommendation_engine_service
            if recommendation_engine_service is not None
            else RecommendationEngineService()
        )
        self._dataset_loader = dataset_loader if dataset_loader is not None else DatasetLoader()
        self._k_values = k_values if k_values is not None else DEFAULT_K_VALUES
        self._latency_metrics_enabled = (
            latency_metrics_enabled
            if latency_metrics_enabled is not None
            else settings.evaluation.latency_metrics_enabled
        )
        self._model_registry = model_registry if model_registry is not None else ModelRegistry()

    @observe(name="retrieval_benchmark_run")
    async def evaluate(
        self,
        queries: list[EvaluationQuery] | None = None,
        *,
        reranking_enabled: bool | None = None,
    ) -> BenchmarkReport:
        """Evaluate `queries` (or the full configured dataset when omitted).

        `reranking_enabled` (Phase 11) forces every evaluated system's own
        reranking on or off for this run, overriding each service's
        configured default — `None` (the default) leaves each service's
        own configuration untouched. See `compare_reranking` for running
        both ways at once and diffing the result.

        Raises `EvaluationException` if loading the default dataset fails
        (only relevant when `queries` is omitted) or if aggregating the
        otherwise successfully-computed per-query results fails
        unexpectedly. See class docstring for why an individual query's
        own failure doesn't raise.
        """
        start = time.monotonic()
        resolved_queries = queries if queries is not None else self._dataset_loader.load()

        query_results = [
            await self._evaluate_one(query, reranking_enabled=reranking_enabled)
            for query in resolved_queries
        ]

        try:
            overall_metrics = _aggregate(query_results, k_values=self._k_values)
        except Exception as exc:
            raise EvaluationException("Failed to aggregate evaluation metrics.") from exc

        total_duration = time.monotonic() - start
        failure_count = sum(1 for result in query_results if result.error is not None)

        update_active_span(
            metadata={
                "queries_count": len(resolved_queries),
                "reranking_enabled": reranking_enabled,
                "failure_count": failure_count,
                "duration_seconds": total_duration,
            }
        )

        if overall_metrics:
            if 10 in overall_metrics.ndcg:
                record_trace_score(name="ndcg@10", value=overall_metrics.ndcg[10])
            record_trace_score(name="mrr", value=overall_metrics.mrr)
            if 5 in overall_metrics.hit_rate:
                record_trace_score(name="hit_rate@5", value=overall_metrics.hit_rate[5])
            if 5 in overall_metrics.precision:
                record_trace_score(name="precision@5", value=overall_metrics.precision[5])

        logger.info(
            "Evaluation run complete: queries=%d, failures=%d, duration=%.4fs",
            len(query_results),
            failure_count,
            total_duration,
        )
        return BenchmarkReport(
            generated_at=datetime.now(UTC),
            dataset_size=len(resolved_queries),
            overall_metrics=overall_metrics,
            query_results=query_results,
            total_duration_seconds=total_duration,
            failure_count=failure_count,
            models=_active_models(self._model_registry),
        )

    async def compare_reranking(
        self, queries: list[EvaluationQuery] | None = None
    ) -> RerankComparisonReport:
        """Evaluate the same `queries` with reranking forced off, then forced on, and diff the metrics.

        The phase's own worked example ("MRR: Before 0.81, After 0.90")
        — this is what produces that comparison. The dataset is loaded
        once (if `queries` is omitted) so both runs evaluate the exact
        same queries; `RERANKER__*` settings still control *how*
        reranking behaves, only whether it runs at all is overridden
        here. Raises whatever either `evaluate()` call raises.
        """
        resolved_queries = queries if queries is not None else self._dataset_loader.load()
        without_reranking = await self.evaluate(resolved_queries, reranking_enabled=False)
        with_reranking = await self.evaluate(resolved_queries, reranking_enabled=True)
        return RerankComparisonReport(
            without_reranking=without_reranking,
            with_reranking=with_reranking,
            improvement=_compute_improvement(without_reranking, with_reranking),
        )

    async def _evaluate_one(
        self, query: EvaluationQuery, *, reranking_enabled: bool | None = None
    ) -> EvaluationQueryResult:
        start = time.monotonic()
        try:
            retrieved = await self._retrieve(query, reranking_enabled=reranking_enabled)
        except Exception as exc:
            logger.warning(
                "Evaluation query failed: query_id=%s, task_type=%s, error=%s",
                query.query_id,
                query.task_type.value,
                exc,
            )
            return EvaluationQueryResult(
                query_id=query.query_id, task_type=query.task_type, error=str(exc)
            )

        latency = time.monotonic() - start if self._latency_metrics_enabled else 0.0
        expected = set(query.ground_truth.expected_products)

        return EvaluationQueryResult(
            query_id=query.query_id,
            task_type=query.task_type,
            retrieved_products=retrieved,
            latency_seconds=latency,
            precision_at_k={k: _precision_at_k(retrieved, expected, k) for k in self._k_values},
            recall_at_k={k: _recall_at_k(retrieved, expected, k) for k in self._k_values},
            ndcg_at_k={k: _ndcg_at_k(retrieved, expected, k) for k in self._k_values},
            hit_rate_at_k={k: _hit_rate_at_k(retrieved, expected, k) for k in self._k_values},
            reciprocal_rank=_reciprocal_rank(retrieved, expected),
        )

    async def _retrieve(
        self, query: EvaluationQuery, *, reranking_enabled: bool | None = None
    ) -> list[UUID]:
        """Dispatch `query` to the system its `task_type` names, returning ranked product IDs."""
        resolved_top_k = query.top_k if query.top_k is not None else settings.evaluation.top_k

        if query.task_type is EvaluationTaskType.RETRIEVAL:
            if not query.text or not query.text.strip():
                raise EvaluationException(
                    f"query '{query.query_id}': image-based evaluation queries are not "
                    "yet supported (see EvaluationQuery.image_path's own docstring)."
                )
            results = await self._hybrid_search_service.search(
                text=query.text, top_k=resolved_top_k, reranking_enabled=reranking_enabled
            )
            return [result.product_id for result in results]

        if query.task_type is EvaluationTaskType.RECOMMENDATION:
            assert query.product_id is not None  # validated by EvaluationQuery
            recommendation_result = await self._recommendation_engine_service.recommend(
                product_id=query.product_id,
                recommendation_type=RecommendationType.SIMILAR,
                top_k=resolved_top_k,
                reranking_enabled=reranking_enabled,
            )
            return [
                recommendation.product_id
                for recommendation in recommendation_result.recommendations
            ]

        # DUPLICATE
        assert query.product_id is not None  # validated by EvaluationQuery
        decision = await self._duplicate_detection_service.detect_by_product_id(
            query.product_id, top_k=resolved_top_k, reranking_enabled=reranking_enabled
        )
        return [candidate.product_id for candidate in decision.top_candidates]


def _aggregate(
    query_results: list[EvaluationQueryResult], *, k_values: tuple[int, ...]
) -> dict[str, RetrievalMetrics]:
    """Average every metric across each `task_type`'s own successfully-evaluated queries.

    A query that errored contributes nothing to its task type's averages
    (its metrics are all at their zero default) but is still counted in
    `BenchmarkReport.failure_count`/`query_results` — excluding failed
    queries from the metric averages keeps a few bad product IDs from
    silently dragging down an otherwise-healthy system's reported quality.
    """
    by_task_type: dict[EvaluationTaskType, list[EvaluationQueryResult]] = {}
    for result in query_results:
        if result.error is not None:
            continue
        by_task_type.setdefault(result.task_type, []).append(result)

    overall_metrics: dict[str, RetrievalMetrics] = {}
    for task_type, results in by_task_type.items():
        count = len(results)
        overall_metrics[task_type.value] = RetrievalMetrics(
            precision_at_k={k: _mean(r.precision_at_k[k] for r in results) for k in k_values},
            recall_at_k={k: _mean(r.recall_at_k[k] for r in results) for k in k_values},
            ndcg_at_k={k: _mean(r.ndcg_at_k[k] for r in results) for k in k_values},
            hit_rate_at_k={k: _mean(r.hit_rate_at_k[k] for r in results) for k in k_values},
            mrr=_mean(r.reciprocal_rank for r in results),
            average_latency_seconds=_mean(r.latency_seconds for r in results),
            query_count=count,
        )
    return overall_metrics


def _mean(values: Iterable[float]) -> float:
    resolved = list(values)
    return sum(resolved) / len(resolved) if resolved else 0.0


def _active_models(model_registry: ModelRegistry) -> list[ModelInfo]:
    """Snapshot whichever model is currently `ACTIVE`, per `ModelType`.

    A type with no active model (every version explicitly deactivated) is
    silently omitted rather than failing the whole evaluation run — the
    model registry's own lifecycle state, not something evaluation should
    have an opinion about.
    """
    active: list[ModelInfo] = []
    for model_type in ModelType:
        try:
            active.append(model_registry.get_active_model(model_type))
        except ResourceNotFoundException:
            continue
    return active


def _compute_improvement(
    without: BenchmarkReport, with_: BenchmarkReport
) -> dict[str, dict[str, float]]:
    """Diff two reports' `overall_metrics`, per shared task type: `after - before`.

    A task type present in only one report (e.g. every one of its
    queries failed under one configuration but not the other)
    contributes no delta — there's nothing meaningful to compare it
    against. `K` values are diffed for whichever cutoffs both sides
    actually share, so this works regardless of how `k_values` is
    configured.
    """
    improvement: dict[str, dict[str, float]] = {}
    for task_type in sorted(set(without.overall_metrics) & set(with_.overall_metrics)):
        before = without.overall_metrics[task_type]
        after = with_.overall_metrics[task_type]
        deltas: dict[str, float] = {"mrr": after.mrr - before.mrr}
        for label, before_at_k, after_at_k in (
            ("precision", before.precision_at_k, after.precision_at_k),
            ("recall", before.recall_at_k, after.recall_at_k),
            ("ndcg", before.ndcg_at_k, after.ndcg_at_k),
            ("hit_rate", before.hit_rate_at_k, after.hit_rate_at_k),
        ):
            for k in sorted(set(before_at_k) & set(after_at_k)):
                deltas[f"{label}_at_{k}"] = after_at_k[k] - before_at_k[k]
        deltas["average_latency_seconds"] = (
            after.average_latency_seconds - before.average_latency_seconds
        )
        improvement[task_type] = deltas
    return improvement


# --- Metrics (binary relevance: a product is either in `expected` or not) ---


def _precision_at_k(retrieved: list[UUID], expected: set[UUID], k: int) -> float:
    """Fraction of the top-`k` *actually returned* results that are relevant.

    Divides by how many results were actually returned (up to `k`), not
    by `k` itself — a system that legitimately has fewer than `k`
    candidates to return (a small catalog) isn't unfairly penalized for
    not padding its result list.
    """
    top_k = retrieved[:k]
    if not expected or not top_k:
        return 0.0
    relevant = sum(1 for product_id in top_k if product_id in expected)
    return relevant / len(top_k)


def _recall_at_k(retrieved: list[UUID], expected: set[UUID], k: int) -> float:
    """Fraction of all relevant products that appear in the top-`k` results."""
    if not expected:
        return 0.0
    relevant = sum(1 for product_id in retrieved[:k] if product_id in expected)
    return relevant / len(expected)


def _hit_rate_at_k(retrieved: list[UUID], expected: set[UUID], k: int) -> float:
    """`1.0` if any relevant product appears in the top-`k` results, else `0.0`."""
    if not expected:
        return 0.0
    return 1.0 if any(product_id in expected for product_id in retrieved[:k]) else 0.0


def _reciprocal_rank(retrieved: list[UUID], expected: set[UUID]) -> float:
    """`1 / rank` of the first relevant product found, `0.0` if none was (Mean Reciprocal Rank's input)."""
    if not expected:
        return 0.0
    for rank, product_id in enumerate(retrieved, start=1):
        if product_id in expected:
            return 1.0 / rank
    return 0.0


def _ndcg_at_k(retrieved: list[UUID], expected: set[UUID], k: int) -> float:
    """Normalized Discounted Cumulative Gain at `k`, binary relevance.

    `DCG@k = sum(1 / log2(rank + 1) for each relevant hit in the top-k)`,
    normalized by the *ideal* DCG (every relevant product ranked first) so
    the result is always in `[0, 1]` regardless of how many relevant
    products exist.
    """
    if not expected:
        return 0.0

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, product_id in enumerate(retrieved[:k], start=1)
        if product_id in expected
    )
    ideal_hits = min(len(expected), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0
