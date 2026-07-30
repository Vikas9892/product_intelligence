"""FastAPI dependency providers, the RBAC guard, and quota enforcement for the enterprise layer (Phase 19).

`get_auth_context` authenticates the request's API key into an
`AuthContext` (401 on a bad key). `require_permission(permission)` builds
on it to enforce RBAC (403 when the role lacks the permission).
`enforce_quota` builds on it to enforce the tenant's daily quota and
per-minute rate limit (429 when exceeded). All three share one
authentication per request (FastAPI caches `get_auth_context`), so a route
guarding itself with both a permission and quota authenticates only once.
The header name is read from settings at request time so
`ENTERPRISE__API_KEY_HEADER` stays configurable.
"""

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.exceptions.errors import AuthorizationException, QuotaExceededException
from app.models.auth_context import AuthContext
from app.models.role import Permission, role_has_permission
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.quota_repository import QuotaRepository
from app.services.enterprise.authentication_service import AuthenticationService


@lru_cache(maxsize=1)
def get_organization_repository() -> OrganizationRepository:
    """Return the process-wide OrganizationRepository singleton, building it on first call."""
    return OrganizationRepository()


@lru_cache(maxsize=1)
def get_api_key_repository() -> ApiKeyRepository:
    """Return the process-wide ApiKeyRepository singleton, building it on first call."""
    return ApiKeyRepository()


@lru_cache(maxsize=1)
def get_authentication_service() -> AuthenticationService:
    """Return the process-wide AuthenticationService singleton, building it on first call."""
    return AuthenticationService(api_key_repository=get_api_key_repository())


@lru_cache(maxsize=1)
def get_audit_repository() -> AuditRepository:
    """Return the process-wide AuditRepository singleton, building it on first call."""
    return AuditRepository()


@lru_cache(maxsize=1)
def get_quota_repository() -> QuotaRepository:
    """Return the process-wide QuotaRepository singleton, building it on first call."""
    return QuotaRepository()


async def get_auth_context(
    request: Request,
    auth_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> AuthContext:
    """Authenticate the request's API key into an `AuthContext` (401 on a bad key)."""
    raw_key = request.headers.get(settings.enterprise.api_key_header)
    return await auth_service.authenticate(raw_key)


def require_permission(
    permission: Permission,
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a dependency that authenticates the request and enforces `permission`.

    Raises `AuthenticationException` (401) for a missing/invalid key and
    `AuthorizationException` (403) when the key's role doesn't grant
    `permission`.
    """

    async def dependency(
        context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if not role_has_permission(context.role, permission):
            raise AuthorizationException(
                f"Role '{context.role.value}' lacks the '{permission.value}' permission."
            )
        return context

    return dependency


async def enforce_quota(
    context: Annotated[AuthContext, Depends(get_auth_context)],
    quota_repository: Annotated[QuotaRepository, Depends(get_quota_repository)],
) -> AuthContext:
    """Record one request against the tenant's quota, raising `QuotaExceededException` (429) if over.

    A configured limit of `0` disables that check. Enforced *after*
    authentication, so an unauthenticated request never consumes quota.
    """
    daily, minute = await quota_repository.hit(context.tenant_id)
    daily_quota = settings.enterprise.daily_request_quota
    rate_limit = settings.enterprise.rate_limit_per_minute
    if daily_quota and daily > daily_quota:
        raise QuotaExceededException(
            f"Daily request quota of {daily_quota} exceeded for this tenant."
        )
    if rate_limit and minute > rate_limit:
        raise QuotaExceededException(
            f"Rate limit of {rate_limit} requests/minute exceeded for this tenant."
        )
    return context
