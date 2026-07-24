"""Unit tests for `TimingMiddleware`, in isolation from the full app."""

import asyncio

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.timing import RESPONSE_TIME_HEADER, TimingMiddleware

_SIMULATED_HANDLER_DELAY_SECONDS = 0.05


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TimingMiddleware)

    @app.get("/slow")
    async def slow(request: Request) -> dict[str, float | None]:
        await asyncio.sleep(_SIMULATED_HANDLER_DELAY_SECONDS)
        return {"seen_duration_ms": getattr(request.state, "duration_ms", None)}

    return app


class TestTimingMiddleware:
    def test_adds_a_response_time_header(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/slow")

        assert RESPONSE_TIME_HEADER in response.headers
        assert float(response.headers[RESPONSE_TIME_HEADER]) >= 0

    def test_measured_duration_reflects_actual_handler_time(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/slow")

        duration_ms = float(response.headers[RESPONSE_TIME_HEADER])
        # A 5% tolerance absorbs OS timer-resolution jitter (observed on
        # Windows under heavy system load) around asyncio.sleep's minimum
        # guaranteed delay, without weakening what this test actually
        # proves: the measurement tracks real handler time, not just ~0.
        assert duration_ms >= _SIMULATED_HANDLER_DELAY_SECONDS * 1000 * 0.95

    def test_duration_is_available_on_request_state_inside_the_handler(self) -> None:
        # The header is only set *after* call_next returns, so the handler
        # itself can't see the final duration — but request.state.duration_ms
        # only gets set by this middleware's own post-call_next code, i.e.
        # after the handler already ran. Confirms handlers never observe a
        # stale/leftover value from this middleware.
        with TestClient(_build_app()) as client:
            response = client.get("/slow")

        assert response.json()["seen_duration_ms"] is None
