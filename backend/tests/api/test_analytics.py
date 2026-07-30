"""Integration tests for the Phase 18 analytics dashboard endpoints.

Builds the *real* `create_app()` app, overriding `get_analytics_engine`
with a fake — the engine's aggregation is covered by its unit tests; this
suite proves the routes delegate and shape the response, and that the
router is gated on ANALYTICS__ENABLED.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.core.constants import TrendGranularity
from app.dependencies.analytics import get_analytics_engine
from app.models.analytics_event import AnalyticsEvent
from app.models.analytics_report import (
    AnalyticsReport,
    DashboardSummary,
    TrendPoint,
    TrendReport,
)
from app.models.model_analytics import ModelAnalytics, ModelUsage
from app.models.usage_metrics import UsageMetrics
from app.services.analytics.analytics_engine import AnalyticsEngine

_PREFIX = settings.application.api_prefix


class _FakeAnalyticsEngine(AnalyticsEngine):
    def __init__(self) -> None:
        pass

    async def dashboard(self) -> DashboardSummary:
        return DashboardSummary(
            today=UsageMetrics(uploads=2),
            window=UsageMetrics(uploads=10, searches=5, average_processing_seconds=1.5),
            window_days=7,
            active_models=3,
        )

    async def model_analytics(self) -> ModelAnalytics:
        return ModelAnalytics(
            models=[
                ModelUsage(
                    model_type="image_embedding",
                    active_model="clip",
                    active_version="1.0.0",
                    status="active",
                    registered_versions=1,
                )
            ],
            window=UsageMetrics(uploads=10),
            window_days=7,
        )

    async def report(self, *, days: int, period: str, end: date | None = None) -> AnalyticsReport:
        return AnalyticsReport(
            period=period,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            usage=UsageMetrics(uploads=10, average_processing_seconds=1.5),
        )

    async def trend(
        self,
        *,
        event: AnalyticsEvent,
        granularity: TrendGranularity,
        periods: int,
        end: date | None = None,
    ) -> TrendReport:
        return TrendReport(
            metric=event.value,
            granularity=granularity.value,
            points=[TrendPoint(period_start=date(2026, 1, 1), value=5.0)],
        )


@pytest.fixture
def analytics_client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_analytics_engine] = _FakeAnalyticsEngine
    with TestClient(app) as client:
        yield client


class TestDashboard:
    def test_returns_the_dashboard(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(f"{_PREFIX}/analytics/dashboard")

        assert response.status_code == 200
        body = response.json()
        assert body["today"]["uploads"] == 2
        assert body["window"]["searches"] == 5
        assert body["window_days"] == 7
        assert body["active_models"] == 3


class TestModels:
    def test_returns_model_inventory(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(f"{_PREFIX}/analytics/models")

        assert response.status_code == 200
        body = response.json()
        assert body["models"][0]["active_model"] == "clip"
        assert body["models"][0]["active_version"] == "1.0.0"


class TestPipeline:
    def test_returns_the_pipeline_report(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(f"{_PREFIX}/analytics/pipeline")

        assert response.status_code == 200
        body = response.json()
        assert body["usage"]["uploads"] == 10
        assert body["usage"]["average_processing_seconds"] == 1.5


class TestTrends:
    def test_returns_json_by_default(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(
            f"{_PREFIX}/analytics/trends", params={"metric": "upload", "granularity": "daily"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["metric"] == "upload"
        assert body["granularity"] == "daily"
        assert body["points"][0]["value"] == 5.0

    def test_returns_markdown_when_requested(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(
            f"{_PREFIX}/analytics/trends", params={"metric": "search", "format": "markdown"}
        )

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "| Period start | Value |" in response.text

    def test_rejects_too_many_periods(self, analytics_client: TestClient) -> None:
        response = analytics_client.get(f"{_PREFIX}/analytics/trends", params={"periods": 1000})

        assert response.status_code == 422


class TestAnalyticsDisabled:
    def test_routes_absent_when_analytics_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.analytics, "enabled", False)
        app = create_app()

        with TestClient(app) as client:
            assert client.get(f"{_PREFIX}/analytics/dashboard").status_code == 404
