"""Unit tests for the FastAPI application factory.

Covers app construction, router/middleware/exception-handler wiring, and
the two settings-driven edge middlewares (CORS, TrustedHost). Behavior of
the other individual custom middlewares (request ID, timing, logging,
security headers) is covered in isolation under `tests/middleware/`; this
file is about how they're all assembled together.
"""

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.application import create_app
from app.core.config import settings
from app.exceptions.base import AppException
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware

_SYSTEM_ROUTE_PATHS = {"/health", "/ready", "/version"}
_BUSINESS_ROUTE_PATHS = {
    f"{settings.application.api_prefix}/products/upload",
    f"{settings.application.api_prefix}/products/search",
    f"{settings.application.api_prefix}/products/check-duplicate",
}

# Expected middleware stack, outermost first — see
# `app.application._register_middleware` for the full ordering rationale.
_EXPECTED_MIDDLEWARE_ORDER: list[type] = [
    TrustedHostMiddleware,
    CORSMiddleware,
    GZipMiddleware,
    SecurityHeadersMiddleware,
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    TimingMiddleware,
]


class TestCreateApp:
    def test_returns_a_fastapi_instance(self) -> None:
        app = create_app()

        assert isinstance(app, FastAPI)

    def test_configures_metadata_from_settings(self) -> None:
        app = create_app()

        assert app.title == settings.application.name
        assert app.version == settings.application.version
        assert app.description

    def test_each_call_returns_a_new_instance(self) -> None:
        first = create_app()
        second = create_app()

        assert first is not second


class TestRouterRegistration:
    def test_registers_exactly_the_expected_routes(self) -> None:
        # `app.openapi()["paths"]` is the stable, public surface for "what
        # endpoints did I register" — unlike `app.routes`, it doesn't
        # include FastAPI's own /docs, /redoc, /openapi.json meta-routes,
        # and it doesn't depend on FastAPI's internal route-storage
        # representation (which has changed across versions).
        app = create_app()

        registered_paths = set(app.openapi()["paths"].keys())

        assert registered_paths == _SYSTEM_ROUTE_PATHS | _BUSINESS_ROUTE_PATHS
        assert not any(
            path.startswith(settings.application.api_prefix) for path in _SYSTEM_ROUTE_PATHS
        )


class TestMiddlewareRegistration:
    def test_registers_middleware_in_the_documented_order(self) -> None:
        app = create_app()

        registered = [cast(type, middleware.cls) for middleware in app.user_middleware]

        assert registered == _EXPECTED_MIDDLEWARE_ORDER


class TestExceptionHandlerRegistration:
    def test_registers_a_handler_for_every_error_path(self) -> None:
        app = create_app()

        assert AppException in app.exception_handlers
        assert RequestValidationError in app.exception_handlers
        assert StarletteHTTPException in app.exception_handlers
        assert Exception in app.exception_handlers


class TestCORSMiddlewareConfiguration:
    def test_default_config_allows_no_cross_origin_access(self) -> None:
        app = create_app()

        with TestClient(app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://not-allowed.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

        assert "access-control-allow-origin" not in response.headers

    def test_allows_an_origin_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.application, "cors_allowed_origins", ["http://example.com"])
        app = create_app()

        with TestClient(app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

        assert response.headers["access-control-allow-origin"] == "http://example.com"


class TestTrustedHostMiddlewareConfiguration:
    def test_default_config_accepts_any_host(self) -> None:
        app = create_app()

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200

    def test_rejects_a_host_outside_the_allow_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.application, "trusted_hosts", ["good.example.com"])
        app = create_app()

        with TestClient(app) as client:  # TestClient's default Host header is "testserver"
            response = client.get("/health")

        assert response.status_code == 400


class TestApplicationStartup:
    def test_app_starts_and_stops_without_error(self) -> None:
        app = create_app()

        with TestClient(app):
            pass
