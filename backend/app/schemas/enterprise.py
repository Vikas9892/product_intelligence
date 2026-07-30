"""Enterprise schemas: the API contract for the `/organizations` //api-keys` //audit` //usage` endpoints (Phase 19).

Deliberately separate from the `app.models` enterprise domain models. The
key security property here is that an `ApiKey` is *never* serialized with
its raw secret: `ApiKeyInfo` (list/metadata) carries only the prefix and
hash-free metadata, and the raw key appears exactly once — in
`ApiKeyCreationResponse.key`, returned only from the create endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.api_key import ApiKey, ApiKeyCreation
from app.models.audit_event import AuditEvent
from app.models.organization import Organization, Tenant
from app.models.role import Role


class OrganizationCreateRequest(BaseModel):
    """Request body for `POST /organizations` (bootstrap)."""

    name: str = Field(min_length=1, max_length=200)


class ApiKeyCreateRequest(BaseModel):
    """Request body for `POST /api-keys`."""

    name: str = Field(min_length=1, max_length=200)
    role: Role = Role.MEMBER


class OrganizationInfo(BaseModel):
    """API-safe view of an `Organization`."""

    id: UUID
    name: str
    created_at: datetime

    @classmethod
    def from_organization(cls, org: Organization) -> "OrganizationInfo":
        return cls(id=org.id, name=org.name, created_at=org.created_at)


class TenantInfo(BaseModel):
    """API-safe view of a `Tenant`."""

    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime

    @classmethod
    def from_tenant(cls, tenant: Tenant) -> "TenantInfo":
        return cls(
            id=tenant.id,
            organization_id=tenant.organization_id,
            name=tenant.name,
            created_at=tenant.created_at,
        )


class ApiKeyInfo(BaseModel):
    """API-safe view of an `ApiKey` — metadata only, never the raw secret."""

    id: UUID
    tenant_id: UUID
    name: str
    role: str
    prefix: str
    revoked: bool
    created_at: datetime

    @classmethod
    def from_api_key(cls, api_key: ApiKey) -> "ApiKeyInfo":
        return cls(
            id=api_key.id,
            tenant_id=api_key.tenant_id,
            name=api_key.name,
            role=api_key.role.value,
            prefix=api_key.prefix,
            revoked=api_key.revoked,
            created_at=api_key.created_at,
        )


class ApiKeyCreationResponse(BaseModel):
    """Response for the create endpoints — the raw `key` is shown here exactly once."""

    api_key: ApiKeyInfo
    key: str

    @classmethod
    def from_creation(cls, creation: ApiKeyCreation) -> "ApiKeyCreationResponse":
        return cls(api_key=ApiKeyInfo.from_api_key(creation.api_key), key=creation.key)


class OrganizationBootstrapResponse(BaseModel):
    """Response for `POST /organizations`: the org, its default tenant, and an owner key."""

    organization: OrganizationInfo
    tenant: TenantInfo
    api_key: ApiKeyCreationResponse


class AuditEventInfo(BaseModel):
    """API-safe view of an `AuditEvent`."""

    id: UUID
    tenant_id: UUID
    actor: str
    action: str
    resource: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_event(cls, event: AuditEvent) -> "AuditEventInfo":
        return cls(
            id=event.id,
            tenant_id=event.tenant_id,
            actor=event.actor,
            action=event.action,
            resource=event.resource,
            metadata=event.metadata,
            created_at=event.created_at,
        )


class UsageResponse(BaseModel):
    """Response body for `GET /usage`."""

    tenant_id: UUID
    requests_today: int
    daily_request_quota: int
    rate_limit_per_minute: int
