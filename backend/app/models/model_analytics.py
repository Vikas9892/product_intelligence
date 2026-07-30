"""Internal domain models: `ModelUsage`, `ModelAnalytics` (Phase 18).

The model-analytics view: per model type (image embedding = CLIP, text
embedding = BGE, reranker = cross-encoder), which model version is active
and how many versions are registered — read straight from the Phase 13
`ModelRegistry` — plus the trailing window's operational usage for
context. Purely a read over the registry and the analytics buckets;
per-model *inference counts* are exposed separately as Prometheus
metrics (`embedding_inference_total{model}`, `rerank_inference_total`),
so this view stays about model *lifecycle/inventory* rather than
re-counting inference.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.usage_metrics import UsageMetrics


class ModelUsage(BaseModel):
    """One model type's active version and registered-version count."""

    model_type: str
    active_model: str | None = None
    active_version: str | None = None
    status: str | None = None
    registered_versions: int = Field(default=0, ge=0)


class ModelAnalytics(BaseModel):
    """The per-model inventory plus the trailing window's usage, for `GET /analytics/models`."""

    models: list[ModelUsage] = Field(default_factory=list)
    window: UsageMetrics
    window_days: int = Field(ge=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
