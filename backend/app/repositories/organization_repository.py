"""`OrganizationRepository`: Redis-backed organizations and tenants (Phase 19).

Persists `Organization` and `Tenant` records as JSON in Redis — no
database, matching this project's Redis-only persistence. Creating an
organization also creates its default tenant, so an account is usable
(has an isolation boundary) the moment it exists. Unlike the analytics
recorder, these operations are only issued by the enterprise admin
endpoints, so they surface Redis failures normally rather than
fail-soft.
"""

from typing import cast
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.models.organization import Organization, Tenant

logger = get_logger(__name__)


class OrganizationRepository:
    """Stores and retrieves organizations and their tenants."""

    def __init__(self, *, redis_client: redis.Redis | None = None) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )

    async def create_organization(self, name: str) -> tuple[Organization, Tenant]:
        """Create an organization and its default tenant, returning both."""
        organization = Organization(name=name)
        tenant = Tenant(organization_id=organization.id, name="default")
        await self._redis.set(_org_key(organization.id), organization.model_dump_json())
        await self._redis.sadd("organizations", str(organization.id))
        await self._save_tenant(tenant)
        logger.info("Organization created: org_id=%s, tenant_id=%s", organization.id, tenant.id)
        return organization, tenant

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        """Return the organization for `organization_id`, or `None`."""
        raw = await self._redis.get(_org_key(organization_id))
        return Organization.model_validate_json(raw) if raw is not None else None

    async def list_organizations(self) -> list[Organization]:
        """Return every organization."""
        ids = await self._redis.smembers("organizations")
        organizations: list[Organization] = []
        for org_id in ids:
            organization = await self.get_organization(UUID(cast(str, org_id)))
            if organization is not None:
                organizations.append(organization)
        return organizations

    async def create_tenant(self, organization_id: UUID, name: str) -> Tenant:
        """Create an additional tenant under `organization_id`."""
        tenant = Tenant(organization_id=organization_id, name=name)
        await self._save_tenant(tenant)
        return tenant

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        """Return the tenant for `tenant_id`, or `None`."""
        raw = await self._redis.get(_tenant_key(tenant_id))
        return Tenant.model_validate_json(raw) if raw is not None else None

    async def list_tenants(self, organization_id: UUID) -> list[Tenant]:
        """Return every tenant under `organization_id`."""
        ids = await self._redis.smembers(_org_tenants_key(organization_id))
        tenants: list[Tenant] = []
        for tenant_id in ids:
            tenant = await self.get_tenant(UUID(cast(str, tenant_id)))
            if tenant is not None:
                tenants.append(tenant)
        return tenants

    async def _save_tenant(self, tenant: Tenant) -> None:
        await self._redis.set(_tenant_key(tenant.id), tenant.model_dump_json())
        await self._redis.sadd(_org_tenants_key(tenant.organization_id), str(tenant.id))


def _org_key(organization_id: UUID) -> str:
    return f"organization:{organization_id}"


def _tenant_key(tenant_id: UUID) -> str:
    return f"tenant:{tenant_id}"


def _org_tenants_key(organization_id: UUID) -> str:
    return f"organization:{organization_id}:tenants"
