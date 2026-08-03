"""Operational and failure-path verification.

Everything here is externally observable behavior a client depends on: the
metrics surface, the headers the frontend reads, how the API refuses bad
input, and that optional features stay off when they are configured off.

Nothing in this module destroys or degrades a service. Failure *injection* --
stopping Redis, filling a disk -- would be a separate, explicitly destructive
suite; a smoke test that broke the deployment it was verifying would be
unusable against staging, let alone production.

The error-shape checks matter more than they look. The frontend renders
`error.code` and `error.message` directly, so a deployment that answers with
a bare string or a raw framework traceback is broken for clients even when
the status code is right.
"""

from __future__ import annotations

import assertions as a
from context import SmokeContext
from dataset import BY_KEY

#: A well-formed UUID that will not exist in any catalog.
_ABSENT_UUID = "00000000-0000-0000-0000-000000000000"

#: Enterprise routes, which must not be publicly readable when the layer is
#: off. Checked as a group because a deployment that gated one and not the
#: others would be a real leak.
_ENTERPRISE_PATHS = (
    "/enterprise/organizations",
    "/enterprise/api-keys",
    "/enterprise/audit",
)


def check_metrics_exposed(ctx: SmokeContext) -> str:
    """GET /metrics serves Prometheus text.

    Treated as optional: METRICS__PROMETHEUS_ENABLED=false is a legitimate
    configuration, and reporting it as a failure would make the suite wrong
    about a correctly configured deployment.
    """
    response = ctx.client.get(ctx.client.url("/metrics"))
    if response.status == 404:
        return "not exposed (Prometheus endpoint disabled)"

    a.status_is(response, 200)
    body = response.text
    a.require(
        "# HELP" in body or "# TYPE" in body,
        "GET /metrics returned 200 but the body carries no Prometheus HELP/TYPE "
        f"lines, so it is not scrapeable. First 200 bytes: {body[:200]!r}",
    )
    return f"{len(body.splitlines())} lines of Prometheus exposition"


def check_system_stats(ctx: SmokeContext) -> str:
    """GET /system/stats reports the operational snapshot dashboards read."""
    response = ctx.client.get(ctx.client.api("/system/stats"))
    if response.status == 404:
        return "not exposed (health endpoints disabled)"

    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/system/stats")
    a.has_keys(
        payload,
        ("uptime_seconds", "worker_concurrency", "queue_depth", "dead_letter_size"),
        context="/system/stats",
    )
    a.at_least(payload["uptime_seconds"], 0.0, context="/system/stats.uptime_seconds")
    a.at_least(
        payload["worker_concurrency"], 1, context="/system/stats.worker_concurrency"
    )
    return (
        f"uptime {float(payload['uptime_seconds']):.0f}s, "
        f"workers {payload['worker_concurrency']}, "
        f"queue {payload['queue_depth']}, dlq {payload['dead_letter_size']}"
    )


def check_analytics_available(ctx: SmokeContext) -> str:
    """GET /analytics/dashboard answers with real counters."""
    response = ctx.client.get(ctx.client.api("/analytics/dashboard"))
    if response.status == 404:
        return "not exposed (analytics disabled)"

    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/analytics/dashboard")
    a.has_keys(
        payload, ("today", "window", "window_days"), context="/analytics/dashboard"
    )
    today = a.is_object(payload["today"], context="/analytics/dashboard.today")
    a.has_keys(today, ("uploads", "searches"), context="/analytics/dashboard.today")
    return f"uploads={today['uploads']} searches={today['searches']} over {payload['window_days']}d"


def check_enterprise_gated(ctx: SmokeContext) -> str:
    """Enterprise routes are not publicly readable.

    Asserts the security property rather than a specific status code. With the
    layer off the routes are never registered (404); with it on they are
    registered but require a key (401/403). Both are correct; a 200 without a
    key is the failure, and that is what this catches.
    """
    if ctx.client.api_key:
        return "skipped (an API key was supplied, so the layer is expected to be on)"

    exposed = []
    seen: list[str] = []
    for path in _ENTERPRISE_PATHS:
        response = ctx.client.get(ctx.client.api(path))
        seen.append(f"{path}={response.status}")
        if response.status == 200:
            exposed.append(path)

    a.require(
        not exposed,
        f"enterprise route(s) returned 200 without an API key: {', '.join(exposed)}. "
        f"Tenant data must not be readable unauthenticated. Observed: {', '.join(seen)}",
    )
    return f"all {len(_ENTERPRISE_PATHS)} routes gated ({seen[0].split('=')[1]})"


def check_invalid_upload_rejected(ctx: SmokeContext) -> str:
    """A non-image upload is refused with a typed error.

    Uses a payload that is genuinely not an image, so the rejection comes from
    real validation rather than from a filename check alone.
    """
    response = ctx.client.post_multipart(
        ctx.client.api("/products/upload"),
        fields={"name": "Demo Invalid Upload Probe", "brand": "SmokeTest"},
        files={"file": ("not-an-image.txt", b"this is plain text, not an image")},
    )
    a.status_in(response, (400, 415, 422))
    error = a.is_error_envelope(response)
    return f"HTTP {response.status}, code={error['code']}"


# A corrupt-image check deliberately does NOT live here.
#
# Uploading a file with a .png extension and garbage contents is accepted with
# 202: the upload endpoint validates the extension, and ImageValidator runs its
# integrity check inside the worker. That is a legitimate async design, and the
# worker handles it correctly -- verified by doing it once, which produced a
# clean typed failure ("failed an image integrity check") after exhausting
# retries.
#
# The problem is what that leaves behind. A corrupt image is a *permanent*
# failure, so the job retries to exhaustion and lands in the dead-letter queue,
# where it stays. A smoke suite that poisons the DLQ of the deployment it is
# verifying is a destructive test wearing a smoke test's clothes -- and it
# would break its own pipeline-stage DLQ assertion on the next run. Decoder
# behavior belongs in the backend's unit tests, which already cover it.


def check_malformed_request_rejected(ctx: SmokeContext) -> str:
    """A request missing required fields returns a 422 naming them.

    The frontend surfaces these to users, so `details` carrying the offending
    fields is part of the contract, not a nicety.
    """
    response = ctx.client.post_multipart(
        ctx.client.api("/products/upload"),
        fields={"brand": "SmokeTest"},  # `name` and `file` are required
    )
    a.status_is(response, 422)
    error = a.is_error_envelope(response, expected_code="validation_error")
    details = error["details"]
    a.require(
        isinstance(details, list) and len(details) > 0,
        f"validation error carried details={details!r}; expected a non-empty list "
        f"naming the invalid fields",
    )
    fields = {str(d.get("loc", ["?"])[-1]) for d in details if isinstance(d, dict)}
    a.require(
        "name" in fields and "file" in fields,
        f"validation details named {sorted(fields)}; expected both missing "
        f"required fields ('name', 'file')",
    )
    return f"HTTP 422, details name {sorted(fields)}"


def check_unknown_resource(ctx: SmokeContext) -> str:
    """A well-formed id that does not exist returns 404, not 500."""
    response = ctx.client.get(ctx.client.api(f"/pricing/{_ABSENT_UUID}"))
    a.status_is(response, 404)
    error = a.is_error_envelope(response)
    return f"HTTP 404, code={error['code']}"


def check_malformed_identifier(ctx: SmokeContext) -> str:
    """A syntactically invalid id is a validation error, not a crash."""
    response = ctx.client.get(ctx.client.api("/products/not-a-uuid/status"))
    a.status_is(response, 422)
    a.is_error_envelope(response, expected_code="validation_error")
    return "HTTP 422, typed validation error"


def check_response_headers(ctx: SmokeContext) -> str:
    """Headers the frontend and operators depend on are present.

    X-Response-Time-Ms is the backend's own measurement, which the search
    workspace displays as genuine server latency rather than a client-side
    guess -- the reason the frontend proxies same-origin at all. X-Request-Id
    is what ties a user-visible failure to a log line.
    """
    response = ctx.client.get(ctx.client.api("/system/health"))
    a.status_is(response, 200)

    timing = a.has_header(response, "X-Response-Time-Ms")
    a.in_range(float(timing), 0.0, 600_000.0, context="X-Response-Time-Ms")
    request_id = a.has_header(response, "X-Request-Id")
    a.require(len(request_id) > 0, "X-Request-Id is present but empty")

    # Set by the security middleware; their absence is a real regression.
    for header in ("X-Content-Type-Options", "X-Frame-Options"):
        a.has_header(response, header)

    return f"timing={timing}ms, request-id present, security headers set"


def check_search_rejects_empty_query(ctx: SmokeContext) -> str:
    """Search with neither an image nor text is a typed 422, not a crash."""
    response = ctx.client.post_multipart(
        ctx.client.api("/products/search"), fields={"top_k": 5}
    )
    a.status_is(response, 422)
    error = a.is_error_envelope(response)
    return f"HTTP 422, code={error['code']}"


def check_duplicate_check_requires_image(ctx: SmokeContext) -> str:
    """Duplicate checking without a file is refused rather than guessed at."""
    response = ctx.client.post_multipart(
        ctx.client.api("/products/check-duplicate"),
        fields={"name": BY_KEY["shoe_blue_a"].name},
    )
    a.status_in(response, (400, 422))
    error = a.is_error_envelope(response)
    return f"HTTP {response.status}, code={error['code']}"
