"""Connectivity, health and capability checks.

These run first and, on failure, abort the run. There is no value in reporting
that image search is broken when the API is not answering at all -- the
downstream failures would be noise obscuring the one real finding.

Everything here reads only documented public endpoints.
"""

from __future__ import annotations

import assertions as a
from context import SmokeContext

#: Endpoints the platform must expose for the rest of the suite to mean
#: anything. Checked against the live OpenAPI document rather than assumed, so
#: a deployment serving an older build fails here with a precise message
#: instead of failing obscurely later.
REQUIRED_ROUTES = (
    ("post", "/api/v1/products/upload"),
    ("get", "/api/v1/products/{product_id}/status"),
    ("post", "/api/v1/products/search"),
    ("post", "/api/v1/products/check-duplicate"),
    ("get", "/api/v1/products/{product_id}/recommendations"),
    ("get", "/api/v1/products/{product_id}/explanations"),
    ("get", "/api/v1/pricing/{product_id}"),
    ("get", "/api/v1/system/health"),
)


def check_liveness(ctx: SmokeContext) -> str:
    """GET /health -- the process is up and answering."""
    response = ctx.client.get(ctx.client.url("/health"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/health")
    a.has_keys(payload, ("status",), context="/health")
    a.require(
        payload["status"] == "ok",
        f"/health reported status {payload['status']!r}, expected 'ok'",
    )
    return f"HTTP 200 in {response.elapsed_ms:.0f}ms"


def check_readiness(ctx: SmokeContext) -> str:
    """GET /ready -- this instance is willing to serve traffic."""
    response = ctx.client.get(ctx.client.url("/ready"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/ready")
    a.has_keys(payload, ("status", "checks"), context="/ready")
    return f"status={payload['status']}"


def check_version(ctx: SmokeContext) -> str:
    """GET /version -- identifies what is actually deployed.

    Recorded rather than asserted. Pinning an expected version here would make
    the suite fail on every release, and its job is to verify behavior, not
    to police the version number.
    """
    response = ctx.client.get(ctx.client.url("/version"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/version")
    a.has_keys(payload, ("name", "version", "environment"), context="/version")
    ctx.notes["deployment"] = payload
    return f"{payload['name']} v{payload['version']} ({payload['environment']})"


def check_system_health(ctx: SmokeContext) -> str:
    """GET /system/health -- the backing services the pipeline needs.

    Unlike /health this does touch dependencies, which is exactly why it is
    checked separately. Redis and Qdrant must both be healthy or nothing later
    in the suite can succeed, and a clear failure here is far more useful than
    a mystifying upload timeout three checks later.
    """
    response = ctx.client.get(ctx.client.api("/system/health"))
    if response.status == 404:
        # METRICS__HEALTH_ENDPOINTS_ENABLED=false is a legitimate
        # configuration, not a broken deployment.
        return "not exposed (health endpoints disabled)"

    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="/system/health")
    a.has_keys(
        payload,
        ("redis", "qdrant", "workers", "queue_depth", "active_models"),
        context="/system/health",
    )
    for service in ("redis", "qdrant"):
        a.require(
            payload[service] == "healthy",
            f"/system/health reports {service}={payload[service]!r}, expected 'healthy'. "
            f"The async pipeline cannot function without it.",
        )
    a.at_least(payload["workers"], 1, context="/system/health.workers")
    a.at_least(payload["active_models"], 1, context="/system/health.active_models")

    ctx.notes["system_health"] = payload
    return (
        f"redis={payload['redis']} qdrant={payload['qdrant']} "
        f"workers={payload['workers']} models={payload['active_models']}"
    )


def check_capabilities(ctx: SmokeContext) -> str:
    """The deployment exposes every route this suite depends on.

    Read from the served OpenAPI document, so this reflects what is actually
    mounted rather than what the repository happens to contain.
    """
    response = ctx.client.get(ctx.client.url("/openapi.json"))
    a.status_is(response, 200)
    document = a.is_object(response.json(), context="/openapi.json")
    paths = a.is_object(
        a.get_path(document, "paths", context="/openapi.json"),
        context="/openapi.json paths",
    )

    missing = [
        f"{method.upper()} {path}"
        for method, path in REQUIRED_ROUTES
        if method not in a.is_object(paths.get(path, {}), context=f"paths[{path}]")
    ]
    if missing:
        a.fail(
            "The deployment is missing required endpoint(s): "
            + ", ".join(missing)
            + ". This build cannot be verified by this suite."
        )
    return f"{len(REQUIRED_ROUTES)} required endpoints present"


def check_models_registered(ctx: SmokeContext) -> str:
    """At least one embedding model is registered and active.

    Without a registered model the pipeline would accept uploads and then fail
    every job, which is much harder to diagnose from the far end.
    """
    response = ctx.client.get(ctx.client.api("/models"))
    a.status_is(response, 200)
    payload = response.json()
    # The endpoint returns a bare array today; tolerate a `{"models": [...]}`
    # envelope too, since that is the shape the other list endpoints use and
    # this check should not be the thing that breaks if it is ever normalized.
    models = payload.get("models", payload) if isinstance(payload, dict) else payload
    entries = a.is_list(models, context="/models")
    a.require(
        len(entries) > 0, "/models returned an empty registry; no models are loaded"
    )

    active = [
        m
        for m in entries
        if isinstance(m, dict) and m.get("status") == "active" and m.get("model_name")
    ]
    a.require(
        len(active) > 0,
        f"/models lists {len(entries)} model(s) but none are active; "
        f"the pipeline would accept uploads and then fail every job",
    )

    names = [str(m["model_name"]) for m in active]
    ctx.notes["models"] = names
    return f"{len(active)} active: {', '.join(names[:3])}"
