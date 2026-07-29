"""Internal domain model: `BenchmarkReport`, the full output of one evaluation run.

Built exclusively by `RetrievalEvaluator.evaluate` — see that module's
own docstring for the full pipeline (load dataset, dispatch each query to
the system its `task_type` names, score, aggregate). Both
`scripts/benchmark.py` (Milestone 4) and `POST /evaluation/run`
(Milestone 5) return/serialize this same model, so there's exactly one
shape a benchmark's output can take regardless of how it was triggered.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.evaluation_result import EvaluationQueryResult
from app.models.model_info import ModelInfo
from app.models.retrieval_metrics import RetrievalMetrics


class BenchmarkReport(BaseModel):
    """Aggregate metrics per evaluated system, plus every individual query's own result.

    `overall_metrics` is keyed by `EvaluationTaskType.value`
    (`"retrieval"`/`"recommendation"`/`"duplicate"`) rather than the enum
    itself — plain `str` keys serialize identically across `model_dump()`
    and `model_dump(mode="json")`, and a report consumer (the benchmark
    script's own Markdown renderer, an API client) never needs to know
    `EvaluationTaskType` exists to read this dict. `failure_count` is
    denormalized from `query_results` (a client reading only the summary
    doesn't have to scan every result's `error` field to know whether
    anything failed).

    `models` (Phase 13) is a snapshot of whichever model was `ACTIVE` per
    `ModelType` (via `ModelRegistry`) at the moment this report was
    generated — the "Model -> Metrics -> Timestamp -> Version" record the
    phase spec asks for, letting a later report compare e.g. "CLIP
    ViT-B/32 -> Recall@10 -> 0.91" against a future run's SigLIP/OpenCLIP
    entry without `RetrievalEvaluator` itself needing to know or care
    which embedding model produced the vectors it searched.
    """

    generated_at: datetime
    dataset_size: int = Field(ge=0)
    overall_metrics: dict[str, RetrievalMetrics] = Field(default_factory=dict)
    query_results: list[EvaluationQueryResult] = Field(default_factory=list)
    total_duration_seconds: float = Field(ge=0)
    failure_count: int = Field(default=0, ge=0)
    models: list[ModelInfo] = Field(default_factory=list)
