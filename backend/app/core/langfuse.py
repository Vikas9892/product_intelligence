"""Langfuse observability and semantic retrieval tracing integration.

Provides conditional, zero-overhead tracing and scoring. When
`settings.langfuse.enabled` is False (the default), all decorators and
helpers are no-ops with zero runtime cost.
"""

import contextlib
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_client = None


def get_langfuse_client() -> Any | None:
    """Return the singleton Langfuse client instance if enabled, else None."""
    global _client
    if not settings.langfuse.enabled:
        return None

    if _client is None:
        try:
            from langfuse import Langfuse

            pk = (
                settings.langfuse.public_key.get_secret_value()
                if settings.langfuse.public_key
                else None
            )
            sk = (
                settings.langfuse.secret_key.get_secret_value()
                if settings.langfuse.secret_key
                else None
            )
            if pk and sk:
                _client = Langfuse(
                    public_key=pk,
                    secret_key=sk,
                    host=settings.langfuse.host,
                    debug=settings.langfuse.debug,
                    sample_rate=settings.langfuse.sample_rate,
                )
                logger.info(
                    "Langfuse client initialized: host=%s, sample_rate=%.2f",
                    settings.langfuse.host,
                    settings.langfuse.sample_rate,
                )
            else:
                logger.warning(
                    "Langfuse is enabled but public_key or secret_key is not configured."
                )
        except Exception as exc:
            logger.warning("Failed to initialize Langfuse client: %s", exc)
            _client = None

    return _client


def observe(*args: Any, **kwargs: Any) -> Callable[[F], F]:
    """Conditional @observe decorator.

    When `settings.langfuse.enabled` is True, delegates directly to
    `langfuse.observe`. When disabled, acts as an identity decorator.
    """
    if settings.langfuse.enabled:
        try:
            from langfuse import observe as _langfuse_observe

            return _langfuse_observe(*args, **kwargs)
        except Exception as exc:
            logger.warning("Failed to invoke langfuse.observe: %s", exc)

    def decorator(func: F) -> F:
        return func

    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return decorator


def update_trace_attributes(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_name: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    environment: str | None = None,
) -> Any:
    """Context manager to propagate trace context (request_id, tenant_id, tags)."""
    if not settings.langfuse.enabled:
        return contextlib.nullcontext()

    try:
        from langfuse import propagate_attributes

        return propagate_attributes(
            user_id=user_id,
            session_id=session_id,
            trace_name=trace_name,
            metadata=metadata,
            tags=tags,
            environment=environment,
        )
    except Exception as exc:
        logger.debug("Failed to propagate Langfuse attributes: %s", exc)
        return contextlib.nullcontext()


def update_active_span(
    *,
    name: str | None = None,
    input: Any | None = None,
    output: Any | None = None,
    metadata: dict[str, Any] | None = None,
    status_message: str | None = None,
) -> None:
    """Update current active span with metadata/inputs/outputs if enabled."""
    if not settings.langfuse.enabled:
        return

    try:
        from langfuse import get_client

        client = get_client()
        if client is not None:
            client.update_current_span(
                name=name,
                input=input,
                output=output,
                metadata=metadata,
                status_message=status_message,
            )
    except Exception as exc:
        logger.debug("Failed to update active Langfuse span: %s", exc)


def record_trace_score(
    *,
    name: str,
    value: float | str,
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an evaluation or quality score on the current active trace."""
    if not settings.langfuse.enabled:
        return

    try:
        from langfuse import get_client

        client = get_client()
        if client is not None:
            client.score_current_trace(
                name=name,
                value=value,
                comment=comment,
                metadata=metadata,
            )
    except Exception as exc:
        logger.debug("Failed to record Langfuse score: %s", exc)


def flush_langfuse() -> None:
    """Flush pending Langfuse observations to the server."""
    if not settings.langfuse.enabled:
        return

    try:
        from langfuse import get_client

        client = get_client()
        if client is not None:
            client.flush()
    except Exception as exc:
        logger.debug("Failed to flush Langfuse client: %s", exc)
