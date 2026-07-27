"""Evaluation schemas: the API contract for `POST /evaluation/run` (Phase 10).

Deliberately separate from `app.models.evaluation_*`/`app.models.benchmark_report`
(the internal domain models `RetrievalEvaluator` builds) for the same
reason `app.schemas.product` is kept separate from `app.models.product` —
see that module's docstring. Never exposes a raw embedding vector,
matching every other response schema in this codebase.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    """Optionally restricts one evaluation run to a subset of the configured dataset.

    Every field defaults to `None` ("run everything") — a caller can
    `POST` with an empty body (or omit it entirely) to run the full
    dataset, matching `scripts/benchmark.py`'s own default behavior.
    `query_ids` and `limit` can be combined: `query_ids` filters first,
    `limit` then caps however many of those matches actually run.
    """

    query_ids: list[str] | None = Field(
        default=None, description="If given, only run these query IDs."
    )
    limit: int | None = Field(
        default=None, gt=0, description="If given, only run the first N (post-filter) queries."
    )


class EvaluationMetricsInfo(BaseModel):
    """API-safe view of `app.models.retrieval_metrics.RetrievalMetrics`."""

    precision_at_k: dict[int, float] = Field(default_factory=dict)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = Field(default_factory=dict)
    mrr: float = 0.0
    average_latency_seconds: float = 0.0
    query_count: int = 0


class EvaluationQueryResultInfo(BaseModel):
    """API-safe view of `app.models.evaluation_result.EvaluationQueryResult`."""

    query_id: str
    task_type: str
    retrieved_products: list[UUID] = Field(default_factory=list)
    latency_seconds: float = 0.0
    precision_at_k: dict[int, float] = Field(default_factory=dict)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = Field(default_factory=dict)
    reciprocal_rank: float = 0.0
    error: str | None = None


class EvaluationRunResponse(BaseModel):
    """Response body for `POST /api/v1/evaluation/run`.

    `summary` is a short, human-readable one-liner (matching
    `scripts/benchmark.py`'s own console output) for a caller that just
    wants a quick read without parsing the full metrics structure.
    `average_latency_seconds` is computed across *every* successfully-
    evaluated query regardless of task type — a single top-level number
    alongside `overall_metrics`' own per-task-type breakdown, per the
    phase spec's own "Latency" bullet distinct from "Overall Metrics."
    """

    summary: str
    dataset_size: int
    total_duration_seconds: float
    average_latency_seconds: float
    failure_count: int
    overall_metrics: dict[str, EvaluationMetricsInfo] = Field(default_factory=dict)
    query_results: list[EvaluationQueryResultInfo] = Field(default_factory=list)
