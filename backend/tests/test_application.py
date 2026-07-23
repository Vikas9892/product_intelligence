"""Unit tests for the FastAPI application factory."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings

_DEFAULT_ROUTE_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


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

    def test_registers_no_business_routes_yet(self) -> None:
        app = create_app()

        route_paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

        assert route_paths <= _DEFAULT_ROUTE_PATHS


class TestApplicationStartup:
    def test_app_starts_and_stops_without_error(self) -> None:
        app = create_app()

        with TestClient(app):
            pass
