"""`AnalyticsEngine`: aggregates Redis daily buckets into usage reports (Phase 18).

Reads the per-day counters `AnalyticsRepository` records and the model
registry, and produces the analytics layer's outputs: a per-window
`UsageMetrics`, a `DashboardSummary` snapshot, and labeled
`AnalyticsReport`s. Purely a reader — it never records events, never runs
a model. Holds no mutable per-request state, so one instance is safe to
share across concurrent requests.
"""

from datetime import UTC, date, datetime, timedelta

from app.core import constants
from app.core.config import settings
from app.core.constants import TrendGranularity
from app.core.logging import get_logger
from app.models.analytics_event import AnalyticsEvent
from app.models.analytics_report import (
    AnalyticsReport,
    DashboardSummary,
    TrendPoint,
    TrendReport,
)
from app.models.model_analytics import ModelAnalytics, ModelUsage
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.models.usage_metrics import UsageMetrics
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.model_registry import ModelRegistry

logger = get_logger(__name__)


class AnalyticsEngine:
    """Turns recorded daily buckets into usage metrics, dashboards, and reports."""

    def __init__(
        self,
        *,
        repository: AnalyticsRepository | None = None,
        model_registry: ModelRegistry | None = None,
        window_days: int | None = None,
    ) -> None:
        self._repository = repository if repository is not None else AnalyticsRepository()
        self._model_registry = model_registry if model_registry is not None else ModelRegistry()
        self._window_days = (
            window_days if window_days is not None else settings.analytics.window_days
        )

    async def usage(self, *, days: int, end: date | None = None) -> UsageMetrics:
        """Aggregate the last `days` days of usage, ending on `end` (default today, inclusive)."""
        date_list = _last_n_days(days, end=end)
        uploads = await self._sum(AnalyticsEvent.UPLOAD, date_list)
        duplicate_checks = await self._sum(AnalyticsEvent.DUPLICATE_CHECK, date_list)
        recommendations = await self._sum(AnalyticsEvent.RECOMMENDATION, date_list)
        searches = await self._sum(AnalyticsEvent.SEARCH, date_list)
        latency_sum, latency_count = await self._repository.latency_range(date_list)
        average = latency_sum / latency_count if latency_count else 0.0
        return UsageMetrics(
            uploads=uploads,
            duplicate_checks=duplicate_checks,
            recommendations=recommendations,
            searches=searches,
            average_processing_seconds=round(average, 4),
        )

    async def dashboard(self) -> DashboardSummary:
        """Build the at-a-glance dashboard: today's usage, the trailing window, and active models."""
        today = await self.usage(days=1)
        window = await self.usage(days=self._window_days)
        active_models = sum(
            1 for model in self._model_registry.list_models() if model.status is ModelStatus.ACTIVE
        )
        logger.info(
            "Analytics dashboard built: window_days=%d, active_models=%d",
            self._window_days,
            active_models,
        )
        return DashboardSummary(
            today=today,
            window=window,
            window_days=self._window_days,
            active_models=active_models,
        )

    async def model_analytics(self) -> ModelAnalytics:
        """Report each model type's active version and registered-version count, plus window usage."""
        models: list[ModelUsage] = []
        for model_type in ModelType:
            versions = self._model_registry.list_models(model_type)
            active = next((m for m in versions if m.status is ModelStatus.ACTIVE), None)
            models.append(
                ModelUsage(
                    model_type=model_type.value,
                    active_model=active.model_name if active is not None else None,
                    active_version=active.version if active is not None else None,
                    status=active.status.value if active is not None else None,
                    registered_versions=len(versions),
                )
            )
        window = await self.usage(days=self._window_days)
        logger.info("Model analytics built: model_types=%d", len(models))
        return ModelAnalytics(models=models, window=window, window_days=self._window_days)

    async def report(self, *, days: int, period: str, end: date | None = None) -> AnalyticsReport:
        """Build a labeled `AnalyticsReport` over the last `days` days."""
        end_date = end if end is not None else _today()
        usage = await self.usage(days=days, end=end_date)
        return AnalyticsReport(
            period=period,
            start_date=end_date - timedelta(days=days - 1),
            end_date=end_date,
            usage=usage,
        )

    async def trend(
        self,
        *,
        event: AnalyticsEvent,
        granularity: TrendGranularity,
        periods: int,
        end: date | None = None,
    ) -> TrendReport:
        """Build a `TrendReport` for `event` over `periods` fixed-length windows, oldest first.

        Each point sums `event`'s daily counts over one
        `granularity`-length window (1/7/30 days); the newest window ends
        on `end` (inclusive, default today).
        """
        window_days = constants.TREND_GRANULARITY_DAYS[granularity]
        end_date = end if end is not None else _today()
        points: list[TrendPoint] = []
        for period_index in range(periods):
            windows_from_newest = periods - 1 - period_index
            period_end = end_date - timedelta(days=windows_from_newest * window_days)
            period_start = period_end - timedelta(days=window_days - 1)
            days = _days_in_range(period_start, period_end)
            value = float(sum(await self._repository.count_range(event, days)))
            points.append(TrendPoint(period_start=period_start, value=value))
        logger.info(
            "Trend report built: event=%s, granularity=%s, periods=%d",
            event.value,
            granularity.value,
            periods,
        )
        return TrendReport(metric=event.value, granularity=granularity.value, points=points)

    async def _sum(self, event: AnalyticsEvent, days: list[date]) -> int:
        return sum(await self._repository.count_range(event, days))


def _today() -> date:
    return datetime.now(UTC).date()


def _last_n_days(days: int, *, end: date | None = None) -> list[date]:
    """Return the `days` dates ending on `end` (inclusive), oldest first."""
    end_date = end if end is not None else _today()
    return [end_date - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _days_in_range(start: date, end: date) -> list[date]:
    """Return every date from `start` to `end` (inclusive), oldest first."""
    span = (end - start).days + 1
    return [start + timedelta(days=offset) for offset in range(span)]
