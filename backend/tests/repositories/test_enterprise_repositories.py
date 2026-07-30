"""Unit tests for `OrganizationRepository` and `ApiKeyRepository` (fakeredis-backed)."""

from uuid import UUID, uuid4

from fakeredis import aioredis as fake_aioredis

from app.models.api_key import ApiKey
from app.models.role import Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.organization_repository import OrganizationRepository


def _org_repo() -> OrganizationRepository:
    return OrganizationRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))


def _key_repo() -> ApiKeyRepository:
    return ApiKeyRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))


class TestOrganizationRepository:
    async def test_create_makes_a_default_tenant(self) -> None:
        repo = _org_repo()

        org, tenant = await repo.create_organization("Acme")

        assert tenant.organization_id == org.id
        assert tenant.name == "default"

    async def test_get_and_list_organizations(self) -> None:
        repo = _org_repo()
        org, _tenant = await repo.create_organization("Acme")

        assert (await repo.get_organization(org.id)) == org
        assert org in await repo.list_organizations()
        assert await repo.get_organization(uuid4()) is None

    async def test_additional_tenants(self) -> None:
        repo = _org_repo()
        org, default = await repo.create_organization("Acme")

        staging = await repo.create_tenant(org.id, "staging")

        tenants = await repo.list_tenants(org.id)
        assert {t.id for t in tenants} == {default.id, staging.id}
        assert await repo.get_tenant(staging.id) == staging

    async def test_list_skips_ids_with_no_record(self) -> None:
        client = fake_aioredis.FakeRedis(decode_responses=True)
        repo = OrganizationRepository(redis_client=client)
        org, _tenant = await repo.create_organization("Acme")
        # A dangling id in each index set with no backing record.
        await client.sadd("organizations", str(uuid4()))
        await client.sadd(f"organization:{org.id}:tenants", str(uuid4()))

        assert [o.id for o in await repo.list_organizations()] == [org.id]
        assert len(await repo.list_tenants(org.id)) == 1


class TestApiKeyRepository:
    def _key(self, *, tenant_id: UUID | None = None, prefix: str = "pik_abc") -> ApiKey:
        return ApiKey(
            organization_id=uuid4(),
            tenant_id=tenant_id if tenant_id is not None else uuid4(),
            name="ci",
            role=Role.MEMBER,
            prefix=prefix,
            key_hash="hashed",
        )

    async def test_create_and_get_by_prefix(self) -> None:
        repo = _key_repo()
        key = self._key(prefix="pik_xyz")

        await repo.create(key)

        assert (await repo.get_by_prefix("pik_xyz")) == key
        assert await repo.get_by_prefix("missing") is None

    async def test_list_by_tenant(self) -> None:
        repo = _key_repo()
        tenant_id = uuid4()
        await repo.create(self._key(tenant_id=tenant_id, prefix="pik_a"))
        await repo.create(self._key(tenant_id=tenant_id, prefix="pik_b"))
        await repo.create(self._key(prefix="pik_other"))  # different tenant

        keys = await repo.list_by_tenant(tenant_id)

        assert {k.prefix for k in keys} == {"pik_a", "pik_b"}

    async def test_revoke(self) -> None:
        repo = _key_repo()
        await repo.create(self._key(prefix="pik_rev"))

        revoked = await repo.revoke("pik_rev")

        assert revoked is not None
        assert revoked.revoked is True
        assert (await repo.get_by_prefix("pik_rev")).revoked is True  # type: ignore[union-attr]

    async def test_revoke_missing_returns_none(self) -> None:
        assert await _key_repo().revoke("nope") is None

    async def test_list_by_tenant_skips_a_dangling_prefix(self) -> None:
        client = fake_aioredis.FakeRedis(decode_responses=True)
        repo = ApiKeyRepository(redis_client=client)
        tenant_id = uuid4()
        await repo.create(self._key(tenant_id=tenant_id, prefix="pik_real"))
        await client.sadd(f"tenant:{tenant_id}:apikeys", "pik_dangling")  # no backing record

        keys = await repo.list_by_tenant(tenant_id)

        assert {k.prefix for k in keys} == {"pik_real"}
