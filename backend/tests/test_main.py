"""Unit tests for the ASGI entrypoint module."""

from fastapi import FastAPI

from app.core.config import settings
from app.main import app


def test_app_is_a_fastapi_instance() -> None:
    assert isinstance(app, FastAPI)


def test_app_title_matches_settings() -> None:
    assert app.title == settings.application.name
