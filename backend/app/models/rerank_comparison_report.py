"""Internal domain model: `RerankComparisonReport`, a before/after reranking benchmark (Phase 11).

Built exclusively by `RetrievalEvaluator.compare_reranking`
(`app/services/evaluation/retrieval_evaluator.py`) — runs the same
dataset through `RetrievalEvaluator.evaluate` twice (reranking forced
off, then forced on) and diffs the two `BenchmarkReport`s, so an operator
can see the phase spec's own worked example ("MRR: Before 0.81, After
0.90") without hand-computing it from two separate runs.
"""

from pydantic import BaseModel, Field

from app.models.benchmark_report import BenchmarkReport


class RerankComparisonReport(BaseModel):
    """`BenchmarkReport`s with reranking disabled and enabled, plus the metric deltas between them."""

    without_reranking: BenchmarkReport
    with_reranking: BenchmarkReport
    #: `{task_type: {metric_name: with_reranking - without_reranking}}` —
    #: only for task types both reports actually produced metrics for. A
    #: positive delta means reranking improved that metric.
    improvement: dict[str, dict[str, float]] = Field(default_factory=dict)
