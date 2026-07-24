"""Security headers middleware.

Stamps a small, standard set of defensive HTTP response headers onto every
response — the header-only baseline recommended by the OWASP Secure
Headers Project for any HTTP service, regardless of what it does. This is
not a replacement for a tuned Content-Security-Policy, auth-specific
headers, or a real WAF — it's the minimum baseline appropriate before any
authentication, session, or templated-HTML-rendering layer exists (a CSP
strict enough to be useful needs to know what a later milestone will
actually serve, e.g. any Swagger UI CDN assets, so it isn't set here yet).

`setdefault` (not direct assignment) is used so a route that has already
set one of these headers for its own reason wins.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a baseline set of security-related response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
