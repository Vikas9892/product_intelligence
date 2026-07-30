"""Unit tests for the Phase 19 enterprise domain models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.api_key import ApiKey, ApiKeyCreation
from app.models.audit_event import AuditEvent
from app.models.organization import Organization, Tenant
from app.models.role import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    role_has_permission,
)


class TestRolePermissions:
    def test_viewer_can_only_read(self) -> None:
        assert role_has_permission(Role.VIEWER, Permission.READ)
        assert not role_has_permission(Role.VIEWER, Permission.WRITE)

    def test_member_can_write(self) -> None:
        assert role_has_permission(Role.MEMBER, Permission.WRITE)
        assert not role_has_permission(Role.MEMBER, Permission.MANAGE_API_KEYS)

    def test_admin_can_manage_api_keys_but_not_organizations(self) -> None:
        assert role_has_permission(Role.ADMIN, Permission.MANAGE_API_KEYS)
        assert role_has_permission(Role.ADMIN, Permission.VIEW_AUDIT)
        assert not role_has_permission(Role.ADMIN, Permission.MANAGE_ORGANIZATION)

    def test_owner_has_every_permission(self) -> None:
        assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission)
        assert all(role_has_permission(Role.OWNER, p) for p in Permission)

    def test_roles_are_cumulative(self) -> None:
        assert ROLE_PERMISSIONS[Role.VIEWER] <= ROLE_PERMISSIONS[Role.MEMBER]
        assert ROLE_PERMISSIONS[Role.MEMBER] <= ROLE_PERMISSIONS[Role.ADMIN]
        assert ROLE_PERMISSIONS[Role.ADMIN] <= ROLE_PERMISSIONS[Role.OWNER]


class TestOrganizationAndTenant:
    def test_organization_defaults(self) -> None:
        org = Organization(name="Acme")
        assert org.id is not None
        assert org.created_at is not None

    def test_organization_rejects_a_blank_name(self) -> None:
        with pytest.raises(ValidationError):
            Organization(name="")

    def test_tenant_belongs_to_an_organization(self) -> None:
        org_id = uuid4()
        tenant = Tenant(organization_id=org_id, name="prod")
        assert tenant.organization_id == org_id


class TestApiKey:
    def test_stored_record_never_holds_the_raw_key(self) -> None:
        key = ApiKey(
            organization_id=uuid4(),
            tenant_id=uuid4(),
            name="ci",
            role=Role.MEMBER,
            prefix="pik_abc",
            key_hash="hashed",
        )
        assert not hasattr(key, "key")
        assert key.revoked is False

    def test_creation_carries_the_raw_key_once(self) -> None:
        key = ApiKey(
            organization_id=uuid4(),
            tenant_id=uuid4(),
            name="ci",
            role=Role.MEMBER,
            prefix="pik_abc",
            key_hash="hashed",
        )
        creation = ApiKeyCreation(api_key=key, key="pik_abc_secret")
        assert creation.key == "pik_abc_secret"
        assert creation.api_key.prefix == "pik_abc"


class TestAuditEvent:
    def test_defaults(self) -> None:
        event = AuditEvent(tenant_id=uuid4(), actor="pik_abc", action="create_api_key")
        assert event.resource is None
        assert event.metadata == {}
        assert event.created_at is not None
