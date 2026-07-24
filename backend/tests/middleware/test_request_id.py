"""Unit tests for `RequestIDMiddleware`, in isolation from the full app."""

import uuid

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/probe")
    async def probe(request: Request) -> dict[str, str]:
        return {"seen_request_id": request.state.request_id}

    return app


class TestRequestIDMiddleware:
    def test_generates_a_request_id_when_none_is_supplied(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/probe")

        response_request_id = response.headers[REQUEST_ID_HEADER]
        assert uuid.UUID(response_request_id)  # a valid UUID4 string was generated
        assert response.json()["seen_request_id"] == response_request_id

    def test_reuses_a_caller_supplied_request_id(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/probe", headers={REQUEST_ID_HEADER: "caller-supplied-id"})

        assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"
        assert response.json()["seen_request_id"] == "caller-supplied-id"
