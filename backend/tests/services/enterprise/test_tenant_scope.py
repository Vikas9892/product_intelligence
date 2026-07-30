"""Unit tests for `TenantScope`."""

from uuid import uuid4

from app.models.auth_context import AuthContext
from app.models.role import Role
from app.services.enterprise.tenant_scope import TenantScope


class TestTenantScope:
    def test_collection_name_is_tenant_scoped(self) -> None:
        tenant_id = uuid4()
        scope = TenantScope(tenant_id, collection_prefix="tenant")

        assert scope.collection_name("product_images") == f"tenant_{tenant_id}_product_images"

    def test_two_tenants_get_disjoint_collection_names(self) -> None:
        a = TenantScope(uuid4(), collection_prefix="tenant")
        b = TenantScope(uuid4(), collection_prefix="tenant")

        assert a.collection_name("product_text") != b.collection_name("product_text")

    def test_redis_namespace_joins_parts(self) -> None:
        tenant_id = uuid4()
        scope = TenantScope(tenant_id)

        assert scope.redis_namespace("analytics", "count") == (
            f"tenant:{tenant_id}:analytics:count"
        )

    def test_redis_namespace_with_no_parts_is_the_tenant_prefix(self) -> None:
        tenant_id = uuid4()
        scope = TenantScope(tenant_id)

        assert scope.redis_namespace() == f"tenant:{tenant_id}"

    def test_from_auth_uses_the_context_tenant(self) -> None:
        context = AuthContext(
            organization_id=uuid4(),
            tenant_id=uuid4(),
            role=Role.MEMBER,
            api_key_id=uuid4(),
            api_key_prefix="pik_abc",
        )

        scope = TenantScope.from_auth(context)

        assert scope.tenant_id == context.tenant_id
