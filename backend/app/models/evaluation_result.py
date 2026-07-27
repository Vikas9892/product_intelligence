"""Internal domain model: `EvaluationQueryResult`, the outcome of evaluating one query.

Built by `RetrievalEvaluator` for every `EvaluationQuery` it scores — one
per query, regardless of `task_type`, so `BenchmarkReport.query_results`
(`app/models/benchmark_report.py`) is a single uniform list rather than
three parallel per-task-type lists.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.evaluation_query import EvaluationTaskType


class EvaluationQueryResult(BaseModel):
    """What one system actually returned for one query, and how well that scored.

    `error` is set (and every metric left at its default) when evaluating
    this particular query raised — one bad query fails itself, not the
    whole benchmark run; see `RetrievalEvaluator`'s own docstring for why
    failures are collected per-query rather than aborting the run.
    """

    query_id: str
    task_type: EvaluationTaskType
    retrieved_products: list[UUID] = Field(default_factory=list)
    latency_seconds: float = Field(default=0.0, ge=0)
    precision_at_k: dict[int, float] = Field(default_factory=dict)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = Field(default_factory=dict)
    reciprocal_rank: float = Field(default=0.0, ge=0, le=1)
    error: str | None = None
