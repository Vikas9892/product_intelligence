"""Enterprise management endpoints (Phase 19).

Multi-tenancy administration, mounted under
`settings.application.api_prefix` and registered only when
`ENTERPRISE__ENABLED` is on:

- `POST /organizations` — **bootstrap**: create an organization + its
  default tenant + an initial OWNER API key (returned once). This is the
  one open endpoint (how a new account gets its first key); every other
  enterprise route requires a valid key with the right permission. In a
  real deployment this would sit behind a platform-admin gate — see the
  README's security notes.
- `GET /organizations` — list organizations (OWNER).
- `POST /api-keys` / `GET /api-keys` / `DELETE /api-keys/{prefix}` —
  manage the caller's tenant's keys (ADMIN+), audit-logged.
- `GET /audit` — the caller's tenant's audit log (ADMIN+).
- `GET /usage` — the caller's tenant's request usage (ADMIN+).

Thin adapters: delegate to the enterprise repositories/services and shape
the response, never leaking a raw API key except from the create
endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.config import settings
from app.core.logging import get_logger
from app.dependencies.enterprise import (
    get_api_key_repository,
    get_audit_repository,
    get_authentication_service,
    get_organization_repository,
    get_quota_repository,
    require_permission,
)
from app.exceptions.errors import AuthorizationException, ResourceNotFoundException
from app.models.audit_event import AuditEvent
from app.models.auth_context import AuthContext
from app.models.role import ROLE_PERMISSIONS, Permission, Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.quota_repository import QuotaRepository
from app.schemas.enterprise import (
    ApiKeyCreateRequest,
    ApiKeyCreationResponse,
    ApiKeyInfo,
    AuditEventInfo,
    OrganizationBootstrapResponse,
    OrganizationCreateRequest,
    OrganizationInfo,
    TenantInfo,
    UsageResponse,
)
from app.services.enterprise.authentication_service import AuthenticationService

logger = get_logger(__name__)

router = APIRouter(tags=["enterprise"])


@router.post(
    "/organizations",
    response_model=OrganizationBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap a new organization",
    description="Creates an organization, its default tenant, and an initial OWNER API key "
    "(returned once). The one open enterprise endpoint — every other requires a key.",
)
async def create_organization(
    request: OrganizationCreateRequest,
    organization_repository: Annotated[
        OrganizationRepository, Depends(get_organization_repository)
    ],
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> OrganizationBootstrapResponse:
    """Create an organization + default tenant + owner key (bootstrap, no auth)."""
    organization, tenant = await organization_repository.create_organization(request.name)
    creation = await authentication_service.create_api_key(
        organization_id=organization.id, tenant_id=tenant.id, name="owner", role=Role.OWNER
    )
    logger.info("Organization bootstrapped: org_id=%s", organization.id)
    return OrganizationBootstrapResponse(
        organization=OrganizationInfo.from_organization(organization),
        tenant=TenantInfo.from_tenant(tenant),
        api_key=ApiKeyCreationResponse.from_creation(creation),
    )


@router.get(
    "/organizations",
    response_model=list[OrganizationInfo],
    status_code=status.HTTP_200_OK,
    summary="List organizations",
    description="Lists every organization (requires the manage-organization permission).",
)
async def list_organizations(
    _context: Annotated[AuthContext, Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
    organization_repository: Annotated[
        OrganizationRepository, Depends(get_organization_repository)
    ],
) -> list[OrganizationInfo]:
    """List every organization."""
    organizations = await organization_repository.list_organizations()
    return [OrganizationInfo.from_organization(org) for org in organizations]


@router.post(
    "/api-keys",
    response_model=ApiKeyCreationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key",
    description="Creates an API key for the caller's tenant. The new key's role cannot exceed "
    "the caller's own permissions (no privilege escalation). The raw key is returned once.",
)
async def create_api_key(
    request: ApiKeyCreateRequest,
    context: Annotated[AuthContext, Depends(require_permission(Permission.MANAGE_API_KEYS))],
    authentication_service: Annotated[AuthenticationService, Depends(get_authentication_service)],
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> ApiKeyCreationResponse:
    """Create a new API key for the caller's tenant (no privilege escalation)."""
    if not ROLE_PERMISSIONS[request.role] <= ROLE_PERMISSIONS[context.role]:
        raise AuthorizationException(
            f"Role '{context.role.value}' cannot create a key with the higher "
            f"role '{request.role.value}'."
        )
    creation = await authentication_service.create_api_key(
        organization_id=context.organization_id,
        tenant_id=context.tenant_id,
        name=request.name,
        role=request.role,
    )
    await audit_repository.append(
        AuditEvent(
            tenant_id=context.tenant_id,
            actor=context.api_key_prefix,
            action="create_api_key",
            resource=creation.api_key.prefix,
            metadata={"role": request.role.value},
        )
    )
    return ApiKeyCreationResponse.from_creation(creation)


@router.get(
    "/api-keys",
    response_model=list[ApiKeyInfo],
    status_code=status.HTTP_200_OK,
    summary="List the tenant's API keys",
    description="Lists the caller's tenant's API keys (metadata only, never the raw secret).",
)
async def list_api_keys(
    context: Annotated[AuthContext, Depends(require_permission(Permission.MANAGE_API_KEYS))],
    api_key_repository: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
) -> list[ApiKeyInfo]:
    """List the caller's tenant's API keys."""
    keys = await api_key_repository.list_by_tenant(context.tenant_id)
    return [ApiKeyInfo.from_api_key(key) for key in keys]


@router.delete(
    "/api-keys/{prefix}",
    response_model=ApiKeyInfo,
    status_code=status.HTTP_200_OK,
    summary="Revoke an API key",
    description="Revokes one of the caller's tenant's API keys by its prefix.",
)
async def revoke_api_key(
    prefix: str,
    context: Annotated[AuthContext, Depends(require_permission(Permission.MANAGE_API_KEYS))],
    api_key_repository: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> ApiKeyInfo:
    """Revoke `prefix` — only if it belongs to the caller's tenant.

    Raises `ResourceNotFoundException` (404) if no such key exists in this
    tenant, so a caller can't probe or revoke another tenant's keys.
    """
    existing = await api_key_repository.get_by_prefix(prefix)
    if existing is None or existing.tenant_id != context.tenant_id:
        raise ResourceNotFoundException(f"API key '{prefix}' was not found.", resource="api_key")
    revoked = await api_key_repository.revoke(prefix)
    assert revoked is not None  # existed a line above; revoke can't lose it
    await audit_repository.append(
        AuditEvent(
            tenant_id=context.tenant_id,
            actor=context.api_key_prefix,
            action="revoke_api_key",
            resource=prefix,
        )
    )
    return ApiKeyInfo.from_api_key(revoked)


@router.get(
    "/audit",
    response_model=list[AuditEventInfo],
    status_code=status.HTTP_200_OK,
    summary="Read the tenant's audit log",
    description="Returns the caller's tenant's most recent audit events, newest first.",
)
async def list_audit(
    context: Annotated[AuthContext, Depends(require_permission(Permission.VIEW_AUDIT))],
    audit_repository: Annotated[AuditRepository, Depends(get_audit_repository)],
    limit: int = 100,
) -> list[AuditEventInfo]:
    """Return the caller's tenant's audit log."""
    events = await audit_repository.list_for_tenant(context.tenant_id, limit=limit)
    return [AuditEventInfo.from_event(event) for event in events]


@router.get(
    "/usage",
    response_model=UsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Read the tenant's request usage",
    description="Returns the caller's tenant's requests-today count and its configured quotas.",
)
async def get_usage(
    context: Annotated[AuthContext, Depends(require_permission(Permission.VIEW_USAGE))],
    quota_repository: Annotated[QuotaRepository, Depends(get_quota_repository)],
) -> UsageResponse:
    """Return the caller's tenant's usage against its quota."""
    requests_today = await quota_repository.usage(context.tenant_id)
    return UsageResponse(
        tenant_id=context.tenant_id,
        requests_today=requests_today,
        daily_request_quota=settings.enterprise.daily_request_quota,
        rate_limit_per_minute=settings.enterprise.rate_limit_per_minute,
    )
