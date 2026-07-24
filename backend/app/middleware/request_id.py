"""Request/correlation ID middleware.

Every request is assigned a request ID: reused from an inbound
`X-Request-ID` header when a caller (or an upstream service, e.g. an API
gateway) already supplies one — so a single ID stays consistent as a
request hops between services, the "correlation ID" pattern — and
generated fresh (a UUID4) otherwise. The ID is stored on
`request.state.request_id` for every downstream middleware/handler to
read, and echoed back as the `X-Request-ID` response header so a caller
can quote it in a bug report and an operator can grep logs for it.

Must run *outer* of `RequestLoggingMiddleware` so the ID already exists
when that middleware logs its "request started" line — see
`app/application.py::_register_middleware` for the full ordering
rationale.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request/correlation ID to every request and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
