"""Shared pytest fixtures for the backend test suite.

Only fixtures genuinely needed by *multiple* test modules belong here —
anything narrower (e.g. `tests/core/test_logging.py`'s root-logger
snapshot/restore fixture) stays local to the file that needs it, so a
reader of this file only has to hold onto fixtures that actually matter
project-wide.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app


@pytest.fixture
def app() -> FastAPI:
    """A fresh, fully-wired FastAPI application instance.

    Function-scoped — `create_app()` does no I/O, so building a new
    instance per test is cheap and guarantees no state (settings
    monkeypatches, route registration) leaks between tests.
    """
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A `TestClient` bound to the `app` fixture, run as a context manager.

    Using `TestClient` as a context manager triggers the app's lifespan
    (`app/lifespan.py`) — startup before the first request, shutdown after
    the fixture tears down — the same as a real deployment, instead of
    silently skipping it.
    """
    with TestClient(app) as test_client:
        yield test_client
