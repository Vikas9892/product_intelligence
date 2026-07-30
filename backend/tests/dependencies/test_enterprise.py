"""Unit tests for the enterprise DI providers and the `require_permission` RBAC guard."""

from collections.abc import Iterator
from typing import Annotated
from uuid import uuid4

import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies.enterprise import (
    get_api_key_repository,
    get_authentication_service,
    get_organization_repository,
    require_permission,
)
from app.exceptions.base import AppException
from app.exceptions.handlers import register_exception_handlers
from app.models.auth_context import AuthContext
from app.models.role import Permission, Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.services.enterprise.authentication_service import AuthenticationService


class TestProviders:
    def test_singletons_are_cached(self) -> None:
        get_organization_repository.cache_clear()
        get_api_key_repository.cache_clear()
        get_authentication_service.cache_clear()

        assert get_organization_repository() is get_organization_repository()
        assert get_api_key_repository() is get_api_key_repository()
        assert get_authentication_service() is get_authentication_service()


@pytest.fixture
def guard_client() -> Iterator[tuple[TestClient, AuthenticationService]]:
    repo = ApiKeyRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))
    auth_service = AuthenticationService(api_key_repository=repo)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/needs-write")
    async def needs_write(
        context: Annotated[AuthContext, Depends(require_permission(Permission.WRITE))],
    ) -> dict[str, str]:
        return {"tenant_id": str(context.tenant_id)}

    app.dependency_overrides[get_authentication_service] = lambda: auth_service
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, auth_service


class TestRequirePermission:
    def test_401_without_an_api_key(
        self, guard_client: tuple[TestClient, AuthenticationService]
    ) -> None:
        client, _auth = guard_client

        response = client.get("/needs-write")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_error"

    async def test_allows_a_role_with_the_permission(
        self, guard_client: tuple[TestClient, AuthenticationService]
    ) -> None:
        client, auth = guard_client
        creation = await auth.create_api_key(
            organization_id=uuid4(), tenant_id=uuid4(), name="ci", role=Role.MEMBER
        )

        response = client.get("/needs-write", headers={"X-API-Key": creation.key})

        assert response.status_code == 200

    async def test_403_for_a_role_without_the_permission(
        self, guard_client: tuple[TestClient, AuthenticationService]
    ) -> None:
        client, auth = guard_client
        creation = await auth.create_api_key(
            organization_id=uuid4(), tenant_id=uuid4(), name="viewer", role=Role.VIEWER
        )

        response = client.get("/needs-write", headers={"X-API-Key": creation.key})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization_error"


def test_app_exception_is_registered() -> None:
    # Sanity: the enterprise exceptions are AppException subclasses, handled generically.
    from app.exceptions.errors import AuthenticationException

    assert issubclass(AuthenticationException, AppException)
