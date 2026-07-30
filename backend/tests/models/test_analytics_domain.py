"""Unit tests for the Phase 18 analytics domain models."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.analytics_event import AnalyticsEvent
from app.models.analytics_report import (
    AnalyticsReport,
    DashboardSummary,
    TrendPoint,
    TrendReport,
)
from app.models.usage_metrics import UsageMetrics


class TestAnalyticsEvent:
    def test_values(self) -> None:
        assert AnalyticsEvent.UPLOAD.value == "upload"
        assert {e.value for e in AnalyticsEvent} == {
            "upload",
            "duplicate_check",
            "recommendation",
            "search",
        }


class TestUsageMetrics:
    def test_defaults_to_zero(self) -> None:
        usage = UsageMetrics()
        assert usage.uploads == 0
        assert usage.average_processing_seconds == 0.0

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValidationError):
            UsageMetrics(uploads=-1)


class TestAnalyticsReport:
    def test_constructs(self) -> None:
        report = AnalyticsReport(
            period="last_7_days",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            usage=UsageMetrics(uploads=10),
        )
        assert report.usage.uploads == 10
        assert report.generated_at is not None


class TestDashboardSummary:
    def test_constructs(self) -> None:
        summary = DashboardSummary(
            today=UsageMetrics(uploads=1),
            window=UsageMetrics(uploads=10),
            window_days=7,
            active_models=3,
        )
        assert summary.window_days == 7
        assert summary.active_models == 3

    def test_rejects_a_zero_window(self) -> None:
        with pytest.raises(ValidationError):
            DashboardSummary(
                today=UsageMetrics(), window=UsageMetrics(), window_days=0, active_models=1
            )


class TestTrendReport:
    def test_constructs_with_points(self) -> None:
        report = TrendReport(
            metric="uploads",
            granularity="daily",
            points=[TrendPoint(period_start=date(2026, 1, 1), value=5.0)],
        )
        assert report.points[0].value == 5.0

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        report = TrendReport(
            metric="searches",
            granularity="weekly",
            points=[TrendPoint(period_start=date(2026, 1, 1), value=3.0)],
        )
        restored = TrendReport.model_validate(report.model_dump(mode="json"))
        assert restored == report
