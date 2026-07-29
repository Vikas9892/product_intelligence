"""Integration tests for the Prometheus `GET /metrics` endpoint (Phase 14).

Builds the *real* `create_app()` app. No Redis is needed — the queue-state
gauges' Redis polling fails fast (short socket timeout) and reports `0.0`
rather than raising, so a scrape succeeds even with nothing running behind
it.
"""

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings


class TestMetricsDisabled:
    def test_no_metrics_endpoint_when_prometheus_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.metrics, "prometheus_enabled", False)
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 404


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_prometheus_text(self) -> None:
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_exposes_custom_metric_names(self) -> None:
        app = create_app()

        with TestClient(app) as client:
            body = client.get("/metrics").text

        # Custom collectors are registered from startup (create_app calls
        # get_metrics_registry), so they appear even on an idle process.
        assert "product_intelligence_recommendation_requests_total" in body
        assert "product_intelligence_queue_depth" in body
        assert "product_intelligence_worker_jobs_total" in body

    def test_exposes_http_request_metrics(self) -> None:
        app = create_app()

        with TestClient(app) as client:
            client.get("/health")
            body = client.get("/metrics").text

        assert "http_request" in body

    def test_metrics_is_not_in_the_openapi_schema(self) -> None:
        app = create_app()

        assert "/metrics" not in app.openapi()["paths"]
