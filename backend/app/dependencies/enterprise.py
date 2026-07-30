"""FastAPI dependency providers and the RBAC guard for the enterprise layer (Phase 19).

`require_permission(permission)` is the dependency every enterprise route
guards itself with: it reads the configured API-key header, authenticates
it into an `AuthContext` (401 on a bad key), and enforces that the key's
role grants `permission` (403 otherwise) — returning the `AuthContext`
so the route can scope/audit on it. The header name is read from settings
at request time (not baked into a `Header(...)` param) so
`ENTERPRISE__API_KEY_HEADER` stays configurable.
"""

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.exceptions.errors import AuthorizationException
from app.models.auth_context import AuthContext
from app.models.role import Permission, role_has_permission
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.organization_repository import OrganizationRepository
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


def require_permission(
    permission: Permission,
) -> Callable[..., Awaitable[AuthContext]]:
    """Build a dependency that authenticates the request and enforces `permission`.

    Raises `AuthenticationException` (401) for a missing/invalid key and
    `AuthorizationException` (403) when the key's role doesn't grant
    `permission`.
    """

    async def dependency(
        request: Request,
        auth_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    ) -> AuthContext:
        raw_key = request.headers.get(settings.enterprise.api_key_header)
        context = await auth_service.authenticate(raw_key)
        if not role_has_permission(context.role, permission):
            raise AuthorizationException(
                f"Role '{context.role.value}' lacks the '{permission.value}' permission."
            )
        return context

    return dependency
