"""Analytics schemas: the API contract for the `/analytics` endpoints (Phase 18).

Deliberately separate from the `app.models.analytics_*` domain models (the
internal shapes `AnalyticsEngine` builds) for the same reason every other
API schema is kept separate from its domain model. The three read
endpoints (dashboard, models, pipeline) each map a domain object into its
response.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.analytics_report import AnalyticsReport, DashboardSummary
from app.models.model_analytics import ModelAnalytics
from app.models.usage_metrics import UsageMetrics


class UsageMetricsInfo(BaseModel):
    """API-safe view of `UsageMetrics`."""

    uploads: int
    duplicate_checks: int
    recommendations: int
    searches: int
    average_processing_seconds: float

    @classmethod
    def from_usage(cls, usage: UsageMetrics) -> "UsageMetricsInfo":
        return cls(
            uploads=usage.uploads,
            duplicate_checks=usage.duplicate_checks,
            recommendations=usage.recommendations,
            searches=usage.searches,
            average_processing_seconds=usage.average_processing_seconds,
        )


class DashboardResponse(BaseModel):
    """Response body for `GET /analytics/dashboard`."""

    today: UsageMetricsInfo
    window: UsageMetricsInfo
    window_days: int
    active_models: int
    generated_at: datetime

    @classmethod
    def from_summary(cls, summary: DashboardSummary) -> "DashboardResponse":
        return cls(
            today=UsageMetricsInfo.from_usage(summary.today),
            window=UsageMetricsInfo.from_usage(summary.window),
            window_days=summary.window_days,
            active_models=summary.active_models,
            generated_at=summary.generated_at,
        )


class ModelUsageInfo(BaseModel):
    """API-safe view of one `ModelUsage`."""

    model_type: str
    active_model: str | None = None
    active_version: str | None = None
    status: str | None = None
    registered_versions: int


class ModelAnalyticsResponse(BaseModel):
    """Response body for `GET /analytics/models`."""

    models: list[ModelUsageInfo] = Field(default_factory=list)
    window: UsageMetricsInfo
    window_days: int
    generated_at: datetime

    @classmethod
    def from_analytics(cls, analytics: ModelAnalytics) -> "ModelAnalyticsResponse":
        return cls(
            models=[
                ModelUsageInfo(
                    model_type=m.model_type,
                    active_model=m.active_model,
                    active_version=m.active_version,
                    status=m.status,
                    registered_versions=m.registered_versions,
                )
                for m in analytics.models
            ],
            window=UsageMetricsInfo.from_usage(analytics.window),
            window_days=analytics.window_days,
            generated_at=analytics.generated_at,
        )


class AnalyticsReportResponse(BaseModel):
    """Response body for `GET /analytics/pipeline` (a labeled window report)."""

    period: str
    start_date: date
    end_date: date
    usage: UsageMetricsInfo
    generated_at: datetime

    @classmethod
    def from_report(cls, report: AnalyticsReport) -> "AnalyticsReportResponse":
        return cls(
            period=report.period,
            start_date=report.start_date,
            end_date=report.end_date,
            usage=UsageMetricsInfo.from_usage(report.usage),
            generated_at=report.generated_at,
        )
