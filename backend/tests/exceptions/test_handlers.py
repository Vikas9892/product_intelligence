"""Integration tests for the global exception handlers.

Builds a throwaway FastAPI app (not the real `create_app()`) with
`register_exception_handlers` applied and a handful of routes that
deliberately raise each error type — this exercises the real
FastAPI/Starlette exception-dispatch machinery end-to-end, which a plain
unit test calling the handler functions directly with a hand-built
`Request` could not.

`raise_server_exceptions=False` is required on the `TestClient` used for
the unhandled-exception case: Starlette's `ServerErrorMiddleware` sends the
handler's response *and then re-raises the original exception* so
debuggers/test clients can still see the real traceback. By default
`TestClient` re-raises that exception into the test itself instead of
returning a `Response` — passing `raise_server_exceptions=False` disables
that so the 500 response can actually be asserted on.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.exceptions.errors import (
    ConflictException,
    ResourceNotFoundException,
    ValidationException,
)
from app.exceptions.handlers import _error_code_for_status, register_exception_handlers


class _Item(BaseModel):
    name: str


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom/not-found")
    async def _raise_not_found() -> None:
        raise ResourceNotFoundException("widget 42 not found", resource="widget")

    @app.get("/boom/conflict")
    async def _raise_conflict() -> None:
        raise ConflictException()

    @app.get("/boom/validation")
    async def _raise_validation() -> None:
        raise ValidationException("end_date must be after start_date")

    @app.get("/boom/http")
    async def _raise_http() -> None:
        raise HTTPException(status_code=404, detail="widget not found (plain HTTPException)")

    @app.get("/boom/unhandled")
    async def _raise_unhandled() -> None:
        raise RuntimeError("some internal secret detail that must never leak")

    @app.post("/echo")
    async def _echo(item: _Item) -> _Item:
        return item

    return app


@pytest.fixture
def client() -> TestClient:
    # raise_server_exceptions=False: see module docstring.
    return TestClient(_build_app(), raise_server_exceptions=False)


class TestAppExceptionHandling:
    def test_resource_not_found_returns_a_consistent_envelope(self, client: TestClient) -> None:
        response = client.get("/boom/not-found")

        assert response.status_code == 404
        assert response.json() == {
            "success": False,
            "error": {
                "code": "resource_not_found",
                "message": "widget 42 not found",
                "details": {"resource": "widget"},
            },
        }

    def test_conflict_exception_uses_its_default_status_and_code(self, client: TestClient) -> None:
        response = client.get("/boom/conflict")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_validation_exception_returns_422(self, client: TestClient) -> None:
        response = client.get("/boom/validation")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert response.json()["error"]["message"] == "end_date must be after start_date"


class TestRequestValidationErrorHandling:
    def test_pydantic_body_validation_failure_uses_the_same_envelope(
        self, client: TestClient
    ) -> None:
        response = client.post("/echo", json={})  # missing required "name"

        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "validation_error"
        assert isinstance(body["error"]["details"], list)
        assert body["error"]["details"][0]["loc"] == ["body", "name"]


class TestHTTPExceptionHandling:
    def test_plain_http_exception_uses_the_same_envelope(self, client: TestClient) -> None:
        response = client.get("/boom/http")

        assert response.status_code == 404
        assert response.json() == {
            "success": False,
            "error": {
                "code": "not_found",
                "message": "widget not found (plain HTTPException)",
                "details": None,
            },
        }


class TestErrorCodeForStatus:
    def test_derives_a_snake_case_code_from_the_reason_phrase(self) -> None:
        assert _error_code_for_status(404) == "not_found"
        assert _error_code_for_status(405) == "method_not_allowed"

    def test_falls_back_to_http_error_for_a_non_standard_status_code(self) -> None:
        assert _error_code_for_status(599) == "http_error"


class TestUnexpectedExceptionHandling:
    def test_unhandled_exception_returns_500_with_a_generic_message(
        self, client: TestClient
    ) -> None:
        response = client.get("/boom/unhandled")

        assert response.status_code == 500
        body = response.json()
        assert body == {
            "success": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": None,
            },
        }

    def test_does_not_leak_the_real_exception_message(self, client: TestClient) -> None:
        response = client.get("/boom/unhandled")

        assert "secret detail" not in response.text
