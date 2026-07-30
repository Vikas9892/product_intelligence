"""Internal domain models: `AnalyticsReport`, `DashboardSummary`, `TrendReport` (Phase 18).

The three shapes the analytics layer produces:

- `DashboardSummary` — an at-a-glance operational snapshot (today's usage,
  the trailing-window usage, and how many models are active).
- `AnalyticsReport` — one labeled time window's `UsageMetrics` with its
  date range, the unit both `GET /analytics/pipeline` and the trend
  exports build on.
- `TrendReport` — a single metric's value over a series of periods
  (daily/weekly/monthly), for the trend endpoint and its JSON/Markdown
  exports.

All are built from the Redis daily buckets and the model registry — never
by re-running any of the activity they describe.
"""

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field

from app.models.usage_metrics import UsageMetrics


class AnalyticsReport(BaseModel):
    """One labeled time window's usage, with its inclusive date range."""

    period: str
    start_date: date
    end_date: date
    usage: UsageMetrics
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DashboardSummary(BaseModel):
    """An at-a-glance operational snapshot for `GET /analytics/dashboard`."""

    today: UsageMetrics
    window: UsageMetrics
    window_days: int = Field(ge=1)
    active_models: int = Field(ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TrendPoint(BaseModel):
    """One period's value in a `TrendReport`."""

    period_start: date
    value: float


class TrendReport(BaseModel):
    """A single metric's value across a series of periods."""

    metric: str
    granularity: str
    points: list[TrendPoint] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
