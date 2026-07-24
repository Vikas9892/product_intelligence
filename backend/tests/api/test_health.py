"""Unit tests for the health/readiness/version endpoints."""

from fastapi.testclient import TestClient

from app.core.config import settings


class TestHealthEndpoint:
    def test_returns_200_and_ok_status(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadyEndpoint:
    def test_returns_200_and_ready_status(self, client: TestClient) -> None:
        response = client.get("/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {}}


class TestVersionEndpoint:
    def test_returns_application_metadata_from_settings(self, client: TestClient) -> None:
        response = client.get("/version")

        assert response.status_code == 200
        assert response.json() == {
            "name": settings.application.name,
            "version": settings.application.version,
            "environment": settings.application.environment.value,
        }
