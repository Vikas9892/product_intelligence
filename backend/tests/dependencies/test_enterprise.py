"""Unit tests for the enterprise DI providers and the `require_permission` RBAC guard."""

from collections.abc import Iterator
from typing import Annotated
from uuid import uuid4

import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.dependencies.enterprise import (
    enforce_quota,
    get_api_key_repository,
    get_audit_repository,
    get_auth_context,
    get_authentication_service,
    get_organization_repository,
    get_quota_repository,
    require_permission,
)
from app.exceptions.base import AppException
from app.exceptions.handlers import register_exception_handlers
from app.models.auth_context import AuthContext
from app.models.role import Permission, Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.quota_repository import QuotaRepository
from app.services.enterprise.authentication_service import AuthenticationService


class TestProviders:
    def test_singletons_are_cached(self) -> None:
        for provider in (
            get_organization_repository,
            get_api_key_repository,
            get_authentication_service,
            get_audit_repository,
            get_quota_repository,
        ):
            provider.cache_clear()
            assert provider() is provider()


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


_CONTEXT = AuthContext(
    organization_id=uuid4(),
    tenant_id=uuid4(),
    role=Role.MEMBER,
    api_key_id=uuid4(),
    api_key_prefix="pik_abc",
)


@pytest.fixture
def quota_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from fastapi import FastAPI

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/quota-guarded")
    async def guarded(
        context: Annotated[AuthContext, Depends(enforce_quota)],
    ) -> dict[str, str]:
        return {"tenant_id": str(context.tenant_id)}

    quota_repo = QuotaRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))
    # Bypass real authentication — quota enforcement is what's under test here.
    app.dependency_overrides[get_auth_context] = lambda: _CONTEXT
    app.dependency_overrides[get_quota_repository] = lambda: quota_repo
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


class TestEnforceQuota:
    def test_allows_requests_under_the_limits(
        self, quota_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.enterprise, "daily_request_quota", 100)
        monkeypatch.setattr(settings.enterprise, "rate_limit_per_minute", 100)

        assert quota_client.get("/quota-guarded").status_code == 200

    def test_429_when_the_rate_limit_is_exceeded(
        self, quota_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.enterprise, "daily_request_quota", 0)  # daily disabled
        monkeypatch.setattr(settings.enterprise, "rate_limit_per_minute", 1)

        assert quota_client.get("/quota-guarded").status_code == 200  # 1st hit ok
        response = quota_client.get("/quota-guarded")  # 2nd hit over the per-minute limit

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "quota_exceeded"

    def test_429_when_the_daily_quota_is_exceeded(
        self, quota_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.enterprise, "daily_request_quota", 1)
        monkeypatch.setattr(settings.enterprise, "rate_limit_per_minute", 0)  # rate limit disabled

        assert quota_client.get("/quota-guarded").status_code == 200
        assert quota_client.get("/quota-guarded").status_code == 429

    def test_disabled_limits_never_throttle(
        self, quota_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.enterprise, "daily_request_quota", 0)
        monkeypatch.setattr(settings.enterprise, "rate_limit_per_minute", 0)

        for _ in range(5):
            assert quota_client.get("/quota-guarded").status_code == 200
