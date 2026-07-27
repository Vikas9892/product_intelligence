"""Internal domain model: `RetrievalMetrics`, aggregate information-retrieval quality metrics.

Standard IR metrics, each computed once per configured `K`
(`EVALUATION_TOP_K`-style cutoffs, typically `1`/`5`/`10`) across a set of
`EvaluationQuery` results for one system (hybrid search, duplicate
detection, or the recommendation engine) — see
`app/services/evaluation/retrieval_evaluator.py` for how each is computed.
"""

from pydantic import BaseModel, Field


class RetrievalMetrics(BaseModel):
    """Aggregate retrieval-quality metrics for one evaluated system, across every query scored.

    `precision_at_k`/`recall_at_k`/`ndcg_at_k`/`hit_rate_at_k` are each
    keyed by `K` (e.g. `{1: 0.8, 5: 0.6, 10: 0.5}`); `mrr` (Mean
    Reciprocal Rank) is a single value — it's already rank-sensitive
    across the whole result list, not naturally "at K" the way the others
    are. `average_latency_seconds` is `0.0` when
    `EVALUATION__LATENCY_METRICS_ENABLED=false` rather than omitted, so a
    report's shape never depends on that setting.
    """

    precision_at_k: dict[int, float] = Field(default_factory=dict)
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    ndcg_at_k: dict[int, float] = Field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = Field(default_factory=dict)
    mrr: float = Field(default=0.0, ge=0, le=1)
    average_latency_seconds: float = Field(default=0.0, ge=0)
    query_count: int = Field(default=0, ge=0)
