"""Unit tests for `RequestLoggingMiddleware`, in isolation from the full app."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware


def _build_app(*, with_request_id: bool, with_timing: bool) -> FastAPI:
    app = FastAPI()
    # Registration order matters: the middleware whose state a later
    # middleware reads must be registered *first* so it ends up innermost
    # (see app.application._register_middleware for the full rationale).
    if with_timing:
        app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    if with_request_id:
        app.add_middleware(RequestIDMiddleware)

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"ok": "true"}

    return app


class TestRequestLoggingMiddlewareStandalone:
    def test_logs_a_start_and_completion_line_with_placeholders(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        with TestClient(_build_app(with_request_id=False, with_timing=False)) as client:
            response = client.get("/probe")

        assert response.status_code == 200
        assert "--> GET /probe [request_id=-]" in caplog.text
        assert "<-- GET /probe 200 [request_id=-] ?ms" in caplog.text


class TestRequestLoggingMiddlewareWithRequestIDAndTiming:
    def test_logs_include_the_real_request_id_and_duration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        with TestClient(_build_app(with_request_id=True, with_timing=True)) as client:
            response = client.get("/probe", headers={"X-Request-ID": "abc-123"})

        assert response.status_code == 200
        assert "--> GET /probe [request_id=abc-123]" in caplog.text
        assert "<-- GET /probe 200 [request_id=abc-123]" in caplog.text
        assert "?ms" not in caplog.text
