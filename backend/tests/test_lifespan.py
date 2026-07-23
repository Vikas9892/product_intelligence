"""Unit tests for the application lifespan (startup/shutdown) behavior."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from app.core import paths
from app.lifespan import lifespan


class TestLifespan:
    async def test_logs_startup_message_before_yielding(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        app = FastAPI()

        async with lifespan(app):
            assert "Starting" in caplog.text
            assert "Shutting down" not in caplog.text

    async def test_logs_shutdown_message_after_the_context_exits(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        app = FastAPI()

        async with lifespan(app):
            pass

        assert "Shutting down" in caplog.text

    async def test_ensures_runtime_directories_on_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_ensure = MagicMock()
        monkeypatch.setattr(paths, "ensure_runtime_directories", mock_ensure)
        app = FastAPI()

        async with lifespan(app):
            mock_ensure.assert_called_once()

    async def test_yields_control_between_startup_and_shutdown(self) -> None:
        app = FastAPI()
        entered = False

        async with lifespan(app):
            entered = True

        assert entered
