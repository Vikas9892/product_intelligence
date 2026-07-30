"""FastAPI application factory.

`create_app()` is the only place `FastAPI(...)` is instantiated — nothing
else in the codebase should construct it directly. A factory (instead of a
module-level `app = FastAPI()`) means every test gets its own fresh
instance instead of importing and mutating one process-wide global.

Application setup is split into three private seams, each called once from
`create_app()` and each responsible for exactly one concern:

- `_register_routers` — API routers (`app.include_router(...)`).
- `_register_exception_handlers` — global error handling.
- `_register_middleware` — cross-cutting request/response behavior.

so adding a router, an exception type, or a middleware in a later milestone
means editing one function, not re-reading and re-deriving `create_app()`
as a whole.
"""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.analytics import router as analytics_router
from app.api.enterprise import router as enterprise_router
from app.api.evaluation import router as evaluation_router
from app.api.explanations import router as explanations_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.models import router as models_router
from app.api.pricing import router as pricing_router
from app.api.products import router as products_router
from app.api.search import router as search_router
from app.api.system import router as system_router
from app.core import constants
from app.core.config import settings
from app.dependencies.metrics import get_metrics_registry
from app.exceptions.handlers import register_exception_handlers
from app.lifespan import lifespan
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing import TimingMiddleware


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application instance."""
    app = FastAPI(
        title=settings.application.name,
        description=constants.DEFAULT_APP_DESCRIPTION,
        version=settings.application.version,
        lifespan=lifespan,
    )

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_routers(app)
    _register_metrics(app)

    return app


def _register_metrics(app: FastAPI) -> None:
    """Instrument `app` for Prometheus and expose `GET /metrics` (Phase 14).

    Gated on `METRICS__PROMETHEUS_ENABLED`: when off, no `/metrics`
    endpoint is registered and no HTTP-request instrumentation is added
    (a deployment that scrapes metrics some other way, or wants none at
    all). `prometheus-fastapi-instrumentator` adds the standard
    `http_request_*` series (Milestone 1's "API requests" tracking) and
    serves them alongside every custom collector this codebase records
    into `prometheus_client`'s process-wide default registry — the same
    registry `MetricsRegistry` uses. `get_metrics_registry()` is called
    here so those custom collectors exist from startup, before any
    business request has constructed a service that would otherwise
    register them lazily — so a `/metrics` scrape of a freshly-started,
    idle process still lists every metric (at its zero value) rather than
    omitting the ones nothing has touched yet. `include_in_schema=False`
    keeps `/metrics` out of the OpenAPI docs (it's an operational
    endpoint, not part of the business API contract), matching how the
    unversioned health routes are treated.
    """
    if not settings.metrics.prometheus_enabled:
        return
    get_metrics_registry()
    instrumentator = Instrumentator()
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)


def _register_routers(app: FastAPI) -> None:
    """Attach API routers to `app`.

    `health_router` (`/health`, `/ready`, `/version`) is deliberately
    unversioned — see `app/api/health.py`. `products_router` and
    `search_router` are real, versioned business routers, so they're
    mounted under `settings.application.api_prefix` (`/api/v1`), giving
    `/api/v1/products/upload` and `/api/v1/products/search`. Both share
    the same `/products` prefix declared on each router individually
    (FastAPI merges routers with the same prefix without conflict) rather
    than one router with two routes, since upload and search are separate
    concerns handled by separate services (`ProductService` vs.
    `SearchService`) — see each router module's own docstring. Further
    business routers are added here the same way, without touching
    application construction/metadata above.

    `system_router` (`/system/health`, `/system/stats`) is gated on
    `METRICS__HEALTH_ENDPOINTS_ENABLED` — a deployment can turn off the
    operational dashboard without affecting the unversioned `/health`/
    `/ready` liveness/readiness probes, which are always registered.
    """
    app.include_router(health_router)
    app.include_router(products_router, prefix=settings.application.api_prefix)
    app.include_router(search_router, prefix=settings.application.api_prefix)
    app.include_router(evaluation_router, prefix=settings.application.api_prefix)
    app.include_router(jobs_router, prefix=settings.application.api_prefix)
    app.include_router(models_router, prefix=settings.application.api_prefix)
    app.include_router(explanations_router, prefix=settings.application.api_prefix)
    if settings.pricing.enabled:
        app.include_router(pricing_router, prefix=settings.application.api_prefix)
    if settings.analytics.enabled:
        app.include_router(analytics_router, prefix=settings.application.api_prefix)
    if settings.enterprise.enabled:
        app.include_router(enterprise_router, prefix=settings.application.api_prefix)
    if settings.metrics.health_endpoints_enabled:
        app.include_router(system_router, prefix=settings.application.api_prefix)


def _register_exception_handlers(app: FastAPI) -> None:
    """Attach the global exception handlers to `app`.

    Delegates entirely to `app.exceptions.handlers` — kept as its own
    module (not inlined here) because the handlers themselves are
    substantial enough to warrant their own file and their own tests,
    independent of app construction.
    """
    register_exception_handlers(app)


def _register_middleware(app: FastAPI) -> None:
    """Attach all middleware to `app`, in a deliberately chosen order.

    Starlette's `add_middleware` *prepends* to an internal list, and the
    final stack is built by wrapping the router in that list's order —
    the practical effect is that **the last `add_middleware` call becomes
    the outermost layer** (the first to see the request, the last to see
    the response). The calls below are ordered innermost-first so the
    resulting runtime order, outermost to innermost, reads top-to-bottom
    as intended:

        TrustedHost -> CORS -> GZip -> SecurityHeaders
            -> RequestID -> RequestLogging -> Timing -> (routing)

    Rationale for that order:

    - `TrustedHostMiddleware` is outermost: reject a forged/invalid `Host`
      header as cheaply as possible, before any other work happens.
    - `CORSMiddleware` next: it must wrap every response, including ones
      built by the exception handlers below, so preflight requests and
      error responses both get correct CORS headers.
    - `GZipMiddleware` next: compresses whatever the inner stack produced,
      so it should be outer relative to anything that sets response
      headers or body content.
    - `SecurityHeadersMiddleware`: same reasoning — must see every
      response, success or error, to stamp its headers onto it.
    - `RequestIDMiddleware` must be outer of `RequestLoggingMiddleware`:
      the ID has to exist on `request.state` before the logging
      middleware's "request started" line is written.
    - `RequestLoggingMiddleware` must be outer of `TimingMiddleware`: a
      middleware's post-`call_next` code only runs after everything inner
      to it has fully finished, so logging can only read the duration
      `TimingMiddleware` computed if timing is inner of logging.
    - `TimingMiddleware` innermost (of the custom stack): its measurement
      should reflect actual request handling, not the overhead of the
      outer layers.

    All of this happens *outside* routing, which itself sits innermost of
    all user middleware (Starlette always places `ExceptionMiddleware`
    directly around the router) — so every middleware here also wraps
    around, and therefore still runs for, a response built by one of the
    exception handlers registered in `_register_exception_handlers`.
    """
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.application.cors_allowed_origins,
        allow_credentials=bool(settings.application.cors_allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.application.trusted_hosts)
