"""HTTP client for the smoke suite.

Standard library only (`urllib`), for the reasons in the package docstring.
That costs one thing -- multipart encoding has to be written by hand, since
`urllib` has no equivalent of `requests`' `files=` -- and buys portability
against any deployment, from a local port to an HTTPS endpoint behind a load
balancer.

The client is deliberately thin. It performs requests and reports what came
back; it makes no judgements about whether a response is acceptable. That
belongs to `assertions`, so failures are described in one consistent voice.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

#: Sent on every request so a smoke run is identifiable in server logs and in
#: access-log analysis after the fact -- useful when a check fails against a
#: shared staging environment and someone has to work out which traffic was
#: the test's.
USER_AGENT = "product-intelligence-smoke/1.0"


@dataclass(frozen=True)
class Response:
    """A completed HTTP exchange.

    Carries the request that produced it so a failure can be reported without
    the assertion layer having to be told separately what was called.
    """

    method: str
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float

    @property
    def text(self) -> str:
        # `replace` rather than `strict`: a body that is not valid UTF-8 is
        # itself a finding worth reporting, and it should surface as a readable
        # assertion failure rather than as a decode traceback from inside the
        # client.
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Parse the body as JSON, or raise `SmokeError` naming the endpoint.

        A non-JSON body from a JSON endpoint usually means a proxy error page
        or a crash, so the message includes a snippet -- "Expecting value" on
        its own would say nothing about what actually came back.
        """
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            snippet = self.text[:200].strip() or "<empty body>"
            raise SmokeError(
                f"{self.method} {self.url} returned HTTP {self.status} with a body that is "
                f"not valid JSON ({exc}). First 200 bytes: {snippet!r}"
            ) from exc

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup (HTTP header names are not case-sensitive)."""
        return self.headers.get(name.lower())


class SmokeError(RuntimeError):
    """A request could not be completed, or its response was unusable.

    Distinct from an assertion failure: this means the suite could not obtain
    an answer at all (connection refused, DNS failure, timeout, unparseable
    body), rather than obtaining one that was wrong.
    """


@dataclass
class SmokeClient:
    """Talks to one deployment of the platform.

    `base_url` is the origin only (`http://localhost:8000`,
    `https://api.example.com`). The API prefix is applied by `api()`, so no
    check ever writes a host or a version prefix inline -- pointing the suite
    at a different deployment is exactly one command-line argument.
    """

    base_url: str
    timeout: float = 30.0
    #: Matches the backend's `APPLICATION__API_PREFIX`. Configurable because a
    #: deployment behind a gateway may mount the API elsewhere.
    api_prefix: str = "/api/v1"
    #: Set only for a deployment using a private/self-signed certificate.
    #: Off by default: silently skipping verification would make the suite
    #: report a passing result against an endpoint it could not authenticate.
    verify_tls: bool = True
    #: Populated when the enterprise layer is enabled; harmless when it is not.
    api_key: str | None = None
    api_key_header: str = "X-API-Key"

    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.verify_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self._ssl_context = context

    # -- URL construction ---------------------------------------------------

    def url(self, path: str) -> str:
        """Absolute URL for a root-level path such as `/health`."""
        return f"{self.base_url}/{path.lstrip('/')}"

    def api(self, path: str) -> str:
        """Absolute URL for a prefixed API path such as `/products/upload`."""
        return f"{self.base_url}{self.api_prefix}/{path.lstrip('/')}"

    # -- Requests -----------------------------------------------------------

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> Response:
        if params:
            # Drop None so callers can pass optional query parameters
            # unconditionally instead of building dicts conditionally.
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url = f"{url}?{urllib.parse.urlencode(clean)}"
        return self._send("GET", url)

    def post_json(self, url: str, payload: dict[str, Any]) -> Response:
        body = json.dumps(payload).encode("utf-8")
        return self._send("POST", url, body=body, content_type="application/json")

    def post_multipart(
        self,
        url: str,
        *,
        fields: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes]] | None = None,
    ) -> Response:
        """POST `multipart/form-data`.

        `files` maps a field name to `(filename, content)`. The upload and
        search endpoints both take this shape.
        """
        body, content_type = _encode_multipart(fields or {}, files or {})
        return self._send("POST", url, body=body, content_type=content_type)

    def _send(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> Response:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.api_key:
            headers[self.api_key_header] = self.api_key

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        started = time.monotonic()

        try:
            # `urlopen` raises HTTPError for 4xx/5xx, but a 404 or 422 is a
            # perfectly good *answer* -- several checks assert on exactly those.
            # HTTPError is itself a response object, so it is unwrapped into a
            # normal Response rather than treated as a failure.
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self._ssl_context
            ) as raw:
                return self._build_response(
                    method, url, raw.status, dict(raw.headers), raw.read(), started
                )
        except urllib.error.HTTPError as exc:
            return self._build_response(
                method, url, exc.code, dict(exc.headers), exc.read(), started
            )
        except urllib.error.URLError as exc:
            # Connection refused, DNS failure, TLS failure, timeout. The most
            # common real cause is "the stack is not running", so say so.
            raise SmokeError(
                f"{method} {url} could not be reached: {exc.reason}. "
                f"Is the deployment running and is --base-url correct?"
            ) from exc
        except TimeoutError as exc:
            raise SmokeError(
                f"{method} {url} timed out after {self.timeout:.0f}s. "
                f"Raise --timeout if this deployment is simply slow."
            ) from exc

    @staticmethod
    def _build_response(
        method: str,
        url: str,
        status: int,
        headers: dict[str, str],
        body: bytes,
        started: float,
    ) -> Response:
        return Response(
            method=method,
            url=url,
            status=status,
            # Lower-cased once here so `header()` lookups are case-insensitive
            # without every call site having to remember that.
            headers={k.lower(): v for k, v in headers.items()},
            body=body,
            elapsed_ms=(time.monotonic() - started) * 1000,
        )


def _encode_multipart(
    fields: dict[str, Any], files: dict[str, tuple[str, bytes]]
) -> tuple[bytes, str]:
    """Encode `multipart/form-data` per RFC 7578.

    Hand-rolled because the standard library has no multipart *encoder* (only
    `cgi`'s long-removed decoder). Roughly thirty lines, versus taking a
    dependency that would have to be installed everywhere the suite runs.
    """
    # token_hex, not a fixed string: a boundary that appeared inside file bytes
    # would corrupt the request, and random 32-hex-char boundaries make that
    # collision impossible in practice.
    boundary = f"----ProductIntelligenceSmoke{secrets.token_hex(16)}"
    parts: list[bytes] = []

    for name, value in fields.items():
        if value is None:
            continue
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )

    for name, (filename, content) in files.items():
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        parts.append(header + content + b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
