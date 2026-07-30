"""Internal domain model: `UsageMetrics`, per-period operational counts (Phase 18).

Aggregates one time window's business activity — how many uploads,
duplicate checks, recommendation requests, and searches happened, plus the
average product-processing latency over that window. Built by
`AnalyticsEngine` from the Redis daily buckets the analytics layer
records into. Purely descriptive: constructing one never triggers any of
the activity it counts.
"""

from pydantic import BaseModel, Field


class UsageMetrics(BaseModel):
    """Counts of the main operational events over one time window, plus average latency."""

    uploads: int = Field(default=0, ge=0)
    duplicate_checks: int = Field(default=0, ge=0)
    recommendations: int = Field(default=0, ge=0)
    searches: int = Field(default=0, ge=0)
    average_processing_seconds: float = Field(default=0.0, ge=0)
