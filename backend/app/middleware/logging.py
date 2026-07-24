"""Request logging middleware.

Logs one line when a request starts and one when it finishes, both
carrying the request ID `RequestIDMiddleware` assigned (that middleware
must run *outer* of this one, so the ID already exists on
`request.state` when this middleware's pre-`call_next` code logs the
"started" line) — so every log line for a single request can be
grepped/correlated by that ID. The completion line also includes the
status code and the duration `TimingMiddleware` computed (that middleware
must run *inner* of this one, so its result is already on `request.state`
by the time this middleware's post-`call_next` code runs). See
`app/application.py::_register_middleware` for the full ordering
rationale.

Named `logging.py` to mirror `app/core/logging.py`'s naming convention —
`import logging` inside a module named `app.middleware.logging`
unambiguously resolves to the stdlib module thanks to Python 3's absolute
imports (see that module's docstring for the same point); this module
doesn't actually need the stdlib module directly, only
`app.core.logging.get_logger`.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log the start and completion of every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = getattr(request.state, "request_id", "-")

        logger.info(
            "--> %s %s [request_id=%s]",
            request.method,
            request.url.path,
            request_id,
        )

        response = await call_next(request)

        duration_ms = getattr(request.state, "duration_ms", None)
        duration_display = f"{duration_ms:.2f}ms" if duration_ms is not None else "?ms"
        logger.info(
            "<-- %s %s %s [request_id=%s] %s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            duration_display,
        )

        return response
