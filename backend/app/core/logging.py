"""Centralized logging configuration.

Configures Python's stdlib `logging` module against
`app.core.config.settings`, so every other module gets a consistently
formatted logger without knowing configuration happened at all:

    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("something happened")

`import logging` below refers to the stdlib module, not this file —
Python 3 imports are absolute by default, so a module named
`app.core.logging` importing top-level `logging` is unambiguous.

Only a console handler is wired up in this milestone. Handlers are built
by `_build_handlers()`, a single seam: adding a file handler later means
adding one line there, and nothing that calls `get_logger()` has to
change.
"""

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


def configure_logging(*, level: str | int | None = None, force: bool = False) -> None:
    """Configure the root logger's level and handlers.

    Idempotent: a second call is a no-op unless `force=True`, so it's safe
    to call from multiple places (e.g. once explicitly at app startup, and
    implicitly via the first `get_logger()` call) without installing
    duplicate handlers or duplicating every log line.

    `level` defaults to `settings.logging.level`; callers (mainly tests)
    can override it explicitly without mutating the global settings
    singleton.
    """
    global _configured
    if _configured and not force:
        return

    resolved_level = level if level is not None else settings.logging.level

    root = logging.getLogger()
    root.setLevel(resolved_level)
    root.handlers[:] = _build_handlers()

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger for `name`, configuring logging on first use.

    Call sites don't need to know whether `configure_logging()` has run
    yet — `get_logger` guarantees it has, so `logger = get_logger(__name__)`
    at module import time always works.
    """
    configure_logging()
    return logging.getLogger(name)


def _build_handlers() -> list[logging.Handler]:
    """All handlers the root logger should have.

    A file handler (or a JSON handler driven by `settings.logging.json_logs`,
    reserved but unused as of this milestone) is added here later — this is
    the only function that needs to change.
    """
    return [_build_console_handler()]


def _build_console_handler() -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_console_formatter())
    return handler


def _console_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
