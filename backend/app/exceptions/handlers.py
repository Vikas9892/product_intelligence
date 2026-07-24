"""Global exception handlers.

`register_exception_handlers(app)` is the single place that decides how
every error path becomes an HTTP response, so no individual route ever has
to build an error response by hand. Four handlers are registered:

1. `AppException` (and every subclass from `errors.py`) — the domain-raised
   path.
2. `RequestValidationError` — FastAPI's own request-schema validation
   failures (missing/mistyped fields), overriding FastAPI's default plain
   `{"detail": [...]}` body with the same envelope everything else uses.
3. `starlette.exceptions.HTTPException` — anything still raised as a plain
   `HTTPException` (framework internals, or third-party dependencies),
   so *nothing* can escape the consistent envelope just by not using
   `AppException`.
4. `Exception` — the catch-all for genuine bugs. Starlette wires a handler
   registered for `Exception` into `ServerErrorMiddleware`, its outermost
   middleware, so this also catches exceptions raised by other middleware,
   not just inside routes.

All four return the same `ErrorResponse` shape from `app/schemas/errors.py`:
`{"success": false, "error": {"code", "message", "details"}}`.
"""

import re
from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.exceptions.base import AppException
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every global exception handler to `app`.

    Called once from `create_app()` (`app/application.py`) — see that
    module for where this fits among the app's other setup.
    """
    app.add_exception_handler(AppException, _handle_app_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected_exception)


async def _handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "Application exception [%s] on %s %s: %s",
        exc.code,
        request.method,
        request.url.path,
        exc.message,
    )
    return _build_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info(
        "Request validation failed on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return _build_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message="The request was invalid.",
        details=exc.errors(),
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    logger.info(
        "HTTP exception %s on %s %s: %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return _build_response(
        status_code=exc.status_code,
        code=_error_code_for_status(exc.status_code),
        message=str(exc.detail),
        details=None,
    )


async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    # `logger.exception` records the full traceback for operators — the
    # response body deliberately never includes it. Leaking exception
    # internals (a raw error message, a stack frame, a SQL fragment) to an
    # API client is an information-disclosure risk, not a debugging aid.
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return _build_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred.",
        details=None,
    )


def _build_response(*, status_code: int, code: str, message: str, details: object) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _error_code_for_status(status_code: int) -> str:
    """Derive a stable `code` string from an HTTP status code's reason phrase.

    E.g. 404 -> "not_found", 405 -> "method_not_allowed". Deriving from
    `HTTPStatus` means every standard status code gets a sensible `code`
    for free, with no hand-maintained status->code mapping to keep in sync.
    """
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        return "http_error"
    return re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")
