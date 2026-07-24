"""Request timing middleware.

Measures how long request handling took using `time.perf_counter` — a
monotonic clock intended for measuring elapsed intervals, unlike
`time.time()`, which can jump backwards or forwards under NTP/clock
adjustments and would produce a wrong (even negative) duration. The result
is stored on `request.state.duration_ms` and echoed back as an
`X-Response-Time-Ms` response header.

Registered as the innermost custom middleware (see
`app/application.py::_register_middleware`) so its measurement is close to
"actual handler time", excluding the overhead of the outer CORS/GZip/
security-headers/request-id/logging layers. Must run *inner* of
`RequestLoggingMiddleware`: that middleware's post-`call_next` code reads
`request.state.duration_ms`, which only exists once this middleware's own
`call_next` has returned and its post-processing has run.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

RESPONSE_TIME_HEADER = "X-Response-Time-Ms"


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure and expose how long request handling took."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        request.state.duration_ms = duration_ms
        response.headers[RESPONSE_TIME_HEADER] = f"{duration_ms:.2f}"
        return response
