"""Unit tests for `AuthenticationService`."""

from uuid import uuid4

import pytest
from fakeredis import aioredis as fake_aioredis

from app.exceptions.errors import AuthenticationException
from app.models.role import Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.services.enterprise.authentication_service import AuthenticationService


def _service() -> tuple[AuthenticationService, ApiKeyRepository]:
    repo = ApiKeyRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))
    return AuthenticationService(api_key_repository=repo), repo


class TestCreateAndAuthenticate:
    async def test_round_trip(self) -> None:
        service, _repo = _service()
        org_id, tenant_id = uuid4(), uuid4()

        creation = await service.create_api_key(
            organization_id=org_id, tenant_id=tenant_id, name="ci", role=Role.ADMIN
        )
        context = await service.authenticate(creation.key)

        assert context.organization_id == org_id
        assert context.tenant_id == tenant_id
        assert context.role is Role.ADMIN
        assert context.api_key_prefix == creation.api_key.prefix

    async def test_raw_key_is_only_in_the_creation(self) -> None:
        service, _repo = _service()

        creation = await service.create_api_key(
            organization_id=uuid4(), tenant_id=uuid4(), name="ci", role=Role.MEMBER
        )

        # The stored record holds only a hash, never the raw key.
        assert creation.api_key.key_hash != creation.key
        assert creation.key.startswith("pik_")


class TestAuthenticateFailures:
    async def test_missing_key_raises(self) -> None:
        service, _repo = _service()

        with pytest.raises(AuthenticationException):
            await service.authenticate(None)

    async def test_unknown_key_raises(self) -> None:
        service, _repo = _service()

        with pytest.raises(AuthenticationException):
            await service.authenticate("pik_does_not_exist")

    async def test_revoked_key_raises(self) -> None:
        service, repo = _service()
        creation = await service.create_api_key(
            organization_id=uuid4(), tenant_id=uuid4(), name="ci", role=Role.MEMBER
        )
        await repo.revoke(creation.api_key.prefix)

        with pytest.raises(AuthenticationException):
            await service.authenticate(creation.key)

    async def test_tampered_key_with_a_valid_prefix_raises(self) -> None:
        service, _repo = _service()
        creation = await service.create_api_key(
            organization_id=uuid4(), tenant_id=uuid4(), name="ci", role=Role.MEMBER
        )
        # Same prefix, wrong secret body.
        tampered = creation.api_key.prefix + "_tampered_suffix"

        with pytest.raises(AuthenticationException):
            await service.authenticate(tampered)
