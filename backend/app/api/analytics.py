"""Analytics dashboard endpoints (Phase 18).

Read-only REST views over the analytics layer, mounted under
`settings.application.api_prefix` (`/api/v1/analytics/...`):

- `GET /analytics/dashboard` — the at-a-glance operational snapshot
  (today's usage, the trailing window, active models).
- `GET /analytics/models` — the model-registry inventory plus window usage.
- `GET /analytics/pipeline` — the trailing window's pipeline throughput and
  average processing latency, as a labeled report.

Thin adapters: delegate to `AnalyticsEngine`, shape the response. The
whole router is registered only when `ANALYTICS__ENABLED` is on.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.constants import ExportFormat, TrendGranularity
from app.core.logging import get_logger
from app.dependencies.analytics import get_analytics_engine
from app.models.analytics_event import AnalyticsEvent
from app.schemas.analytics import (
    AnalyticsReportResponse,
    DashboardResponse,
    ModelAnalyticsResponse,
    TrendReportResponse,
)
from app.services.analytics.analytics_engine import AnalyticsEngine
from app.services.analytics.trend_exporter import to_markdown

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Operational analytics dashboard",
    description="Today's usage, the trailing-window usage, and how many models are active.",
)
async def dashboard(
    analytics_engine: Annotated[AnalyticsEngine, Depends(get_analytics_engine)],
) -> DashboardResponse:
    """Return the at-a-glance operational dashboard."""
    summary = await analytics_engine.dashboard()
    logger.info("Analytics dashboard requested.")
    return DashboardResponse.from_summary(summary)


@router.get(
    "/models",
    response_model=ModelAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Model inventory analytics",
    description="Per model type: the active version, lifecycle status, and registered-version "
    "count, plus the trailing window's usage.",
)
async def model_analytics(
    analytics_engine: Annotated[AnalyticsEngine, Depends(get_analytics_engine)],
) -> ModelAnalyticsResponse:
    """Return the per-model registry inventory and window usage."""
    analytics = await analytics_engine.model_analytics()
    logger.info("Model analytics requested.")
    return ModelAnalyticsResponse.from_analytics(analytics)


@router.get(
    "/pipeline",
    response_model=AnalyticsReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Pipeline throughput and latency",
    description="The trailing window's upload/duplicate/recommendation/search throughput and "
    "average product-processing latency, as a labeled report.",
)
async def pipeline(
    analytics_engine: Annotated[AnalyticsEngine, Depends(get_analytics_engine)],
) -> AnalyticsReportResponse:
    """Return a labeled report of the trailing window's pipeline activity."""
    report = await analytics_engine.report(
        days=settings.analytics.window_days, period="pipeline_window"
    )
    logger.info("Pipeline analytics requested.")
    return AnalyticsReportResponse.from_report(report)


@router.get(
    "/trends",
    response_model=None,
    status_code=status.HTTP_200_OK,
    summary="Trend report for one metric",
    description="Returns a daily/weekly/monthly trend for one event metric, as JSON "
    "(default) or a Markdown table (format=markdown).",
)
async def trends(
    analytics_engine: Annotated[AnalyticsEngine, Depends(get_analytics_engine)],
    metric: Annotated[AnalyticsEvent, Query(description="Which event to trend.")] = (
        AnalyticsEvent.UPLOAD
    ),
    granularity: Annotated[TrendGranularity, Query()] = TrendGranularity.DAILY,
    periods: Annotated[int, Query(gt=0, le=90, description="How many periods to include.")] = 7,
    export_format: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.JSON,
) -> TrendReportResponse | Response:
    """Return a trend report for `metric`, as JSON or Markdown."""
    report = await analytics_engine.trend(event=metric, granularity=granularity, periods=periods)
    logger.info(
        "Trend report requested: metric=%s, granularity=%s, format=%s",
        metric.value,
        granularity.value,
        export_format.value,
    )
    if export_format is ExportFormat.MARKDOWN:
        return PlainTextResponse(to_markdown(report), media_type="text/markdown")
    return TrendReportResponse.from_trend(report)
