"""Unit tests for `SecurityHeadersMiddleware`, in isolation from the full app."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware.security_headers import SecurityHeadersMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    return app


class TestSecurityHeadersMiddleware:
    def test_adds_the_full_baseline_header_set(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/probe")

        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert response.headers["x-permitted-cross-domain-policies"] == "none"
        assert "max-age=31536000" in response.headers["strict-transport-security"]

    def test_does_not_override_a_header_the_route_already_set(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/custom")
        async def custom() -> JSONResponse:
            return JSONResponse(content={"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

        with TestClient(app) as client:
            response = client.get("/custom")

        assert response.headers["x-frame-options"] == "SAMEORIGIN"
