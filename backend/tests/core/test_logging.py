"""Unit tests for the centralized logging configuration."""

import logging
import re
from collections.abc import Iterator

import pytest

from app.core import logging as logging_config
from app.core.config import settings


@pytest.fixture(autouse=True)
def _isolate_root_logger() -> Iterator[None]:
    """Snapshot and restore the real root logger around every test.

    `configure_logging()` mutates the process-wide root logger in place.
    Without this, one test's handlers/level would leak into the next test
    (and into pytest's own log capturing), so every test in this file
    gets a clean, restored root logger regardless of what it does.
    """
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_configured = logging_config._configured

    yield

    root.handlers[:] = original_handlers
    root.setLevel(original_level)
    logging_config._configured = original_configured


class TestConfigureLogging:
    def test_sets_root_level_from_explicit_override(self) -> None:
        logging_config.configure_logging(level="WARNING", force=True)

        assert logging.getLogger().level == logging.WARNING

    def test_defaults_to_level_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings.logging, "level", "ERROR")

        logging_config.configure_logging(force=True)

        assert logging.getLogger().level == logging.ERROR

    def test_installs_exactly_one_console_handler(self) -> None:
        logging_config.configure_logging(force=True)

        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_is_a_no_op_on_second_call_without_force(self) -> None:
        logging_config._configured = False
        logging_config.configure_logging(level="INFO")
        first_handler = logging.getLogger().handlers[0]

        logging_config.configure_logging(level="DEBUG")  # no force -> ignored

        assert logging.getLogger().level == logging.INFO
        assert logging.getLogger().handlers[0] is first_handler

    def test_force_rebuilds_handlers_without_duplicating_them(self) -> None:
        logging_config.configure_logging(force=True)
        logging_config.configure_logging(force=True)

        assert len(logging.getLogger().handlers) == 1


class TestGetLogger:
    def test_returns_a_logger_with_the_given_name(self) -> None:
        logger = logging_config.get_logger("product_intelligence.test")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "product_intelligence.test"

    def test_triggers_configuration_on_first_use(self) -> None:
        logging_config._configured = False
        logging.getLogger().handlers[:] = []

        logging_config.get_logger(__name__)

        assert logging.getLogger().handlers


class TestConsoleFormatter:
    def test_includes_timestamp_level_name_and_message(self) -> None:
        formatter = logging_config._console_formatter()
        record = logging.LogRecord(
            name="app.core.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", formatted)
        assert "INFO" in formatted
        assert "app.core.test" in formatted
        assert "hello world" in formatted


def test_end_to_end_logging_writes_formatted_message_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging_config.configure_logging(level="INFO", force=True)
    logger = logging_config.get_logger("app.core.test_logging")

    logger.info("hello from a test")

    captured = capsys.readouterr()
    assert "hello from a test" in captured.out
    assert "app.core.test_logging" in captured.out
    assert "INFO" in captured.out
