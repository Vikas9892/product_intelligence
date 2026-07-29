"""Evaluation endpoints (Phase 10-11).

`POST /evaluation/run` (mounted under `settings.application.api_prefix`
by `app/application.py`, so `/api/v1/evaluation/run`) runs the configured
evaluation dataset — or a caller-selected subset of it — against hybrid
search, duplicate detection, and the recommendation engine, and returns
aggregate plus per-query metrics. `POST /evaluation/compare-reranking`
(Phase 11) runs the same dataset twice — reranking forced off, then
forced on — and returns both reports plus the metric deltas between them.

Mirrors every other route in this codebase: a thin adapter — parse the
request, delegate to `DatasetLoader`/`RetrievalEvaluator`, shape the
response — with no evaluation or metric-computation logic of its own.
Subset selection (`query_ids`/`limit`) happens here, in the router (shared
by both routes via `_resolve_queries`), not inside `RetrievalEvaluator`
itself: filtering "which queries to run" is a request-shaping concern,
the same way `ProductFilters` narrows a search request before
`HybridSearchService` ever sees it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.evaluation import get_dataset_loader, get_retrieval_evaluator
from app.models.benchmark_report import BenchmarkReport
from app.models.evaluation_query import EvaluationQuery
from app.schemas.evaluation import (
    EvaluationMetricsInfo,
    EvaluationQueryResultInfo,
    EvaluationRunRequest,
    EvaluationRunResponse,
    RerankComparisonResponse,
)
from app.schemas.model import ModelInfoResponse
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import RetrievalEvaluator

logger = get_logger(__name__)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post(
    "/run",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run the evaluation benchmark",
    description="Runs the configured evaluation dataset (or a subset of it, via query_ids/"
    "limit) against hybrid search, duplicate detection, and the recommendation engine, "
    "returning aggregate and per-query metrics.",
)
async def run_evaluation(
    dataset_loader: Annotated[DatasetLoader, Depends(get_dataset_loader)],
    retrieval_evaluator: Annotated[RetrievalEvaluator, Depends(get_retrieval_evaluator)],
    request: EvaluationRunRequest | None = None,
) -> EvaluationRunResponse:
    """Load the dataset, narrow it to `request`'s subset (if any), and evaluate.

    `request` is optional — a caller may `POST` with an empty body or
    omit it entirely to run the full configured dataset.

    Raises whatever `DatasetLoader`/`RetrievalEvaluator` raise on failure
    (`EvaluationException`, converted to the standard error envelope by
    the global handlers).
    """
    queries = _resolve_queries(dataset_loader, request)
    logger.info("Evaluation run requested: queries=%d", len(queries))

    report = await retrieval_evaluator.evaluate(queries)
    return _to_response(report)


@router.post(
    "/compare-reranking",
    response_model=RerankComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare evaluation metrics with reranking disabled vs. enabled",
    description="Runs the configured evaluation dataset (or a subset of it, via query_ids/"
    "limit) twice — once with cross-encoder reranking forced off, once forced on — and "
    "returns both reports plus the metric deltas between them.",
)
async def compare_reranking(
    dataset_loader: Annotated[DatasetLoader, Depends(get_dataset_loader)],
    retrieval_evaluator: Annotated[RetrievalEvaluator, Depends(get_retrieval_evaluator)],
    request: EvaluationRunRequest | None = None,
) -> RerankComparisonResponse:
    """Load the dataset, narrow it to `request`'s subset (if any), and compare reranking.

    Raises whatever `DatasetLoader`/`RetrievalEvaluator` raise on failure
    (`EvaluationException`, converted to the standard error envelope by
    the global handlers).
    """
    queries = _resolve_queries(dataset_loader, request)
    logger.info("Reranking comparison requested: queries=%d", len(queries))

    comparison = await retrieval_evaluator.compare_reranking(queries)
    return RerankComparisonResponse(
        without_reranking=_to_response(comparison.without_reranking),
        with_reranking=_to_response(comparison.with_reranking),
        improvement=comparison.improvement,
    )


def _resolve_queries(
    dataset_loader: DatasetLoader, request: EvaluationRunRequest | None
) -> list[EvaluationQuery]:
    """Load the full configured dataset, narrowed to `request`'s `query_ids`/`limit` subset, if any."""
    resolved_request = request if request is not None else EvaluationRunRequest()
    queries = dataset_loader.load()

    if resolved_request.query_ids is not None:
        wanted = set(resolved_request.query_ids)
        queries = [query for query in queries if query.query_id in wanted]
    if resolved_request.limit is not None:
        queries = queries[: resolved_request.limit]
    return queries


def _to_response(report: BenchmarkReport) -> EvaluationRunResponse:
    latencies = [result.latency_seconds for result in report.query_results if result.error is None]
    average_latency = sum(latencies) / len(latencies) if latencies else 0.0

    return EvaluationRunResponse(
        summary=(
            f"{report.dataset_size} queries evaluated, {report.failure_count} failures, "
            f"{report.total_duration_seconds:.2f}s total."
        ),
        dataset_size=report.dataset_size,
        total_duration_seconds=report.total_duration_seconds,
        average_latency_seconds=average_latency,
        failure_count=report.failure_count,
        overall_metrics={
            task_type: EvaluationMetricsInfo(
                precision_at_k=metrics.precision_at_k,
                recall_at_k=metrics.recall_at_k,
                ndcg_at_k=metrics.ndcg_at_k,
                hit_rate_at_k=metrics.hit_rate_at_k,
                mrr=metrics.mrr,
                average_latency_seconds=metrics.average_latency_seconds,
                query_count=metrics.query_count,
            )
            for task_type, metrics in report.overall_metrics.items()
        },
        query_results=[
            EvaluationQueryResultInfo(
                query_id=result.query_id,
                task_type=result.task_type.value,
                retrieved_products=result.retrieved_products,
                latency_seconds=result.latency_seconds,
                precision_at_k=result.precision_at_k,
                recall_at_k=result.recall_at_k,
                ndcg_at_k=result.ndcg_at_k,
                hit_rate_at_k=result.hit_rate_at_k,
                reciprocal_rank=result.reciprocal_rank,
                error=result.error,
            )
            for result in report.query_results
        ],
        models=[ModelInfoResponse.from_model_info(model_info) for model_info in report.models],
    )
