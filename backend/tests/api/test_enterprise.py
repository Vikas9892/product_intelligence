"""Integration tests for the Phase 19 enterprise endpoints.

Builds the *real* `create_app()` app with `ENTERPRISE__ENABLED` on and the
enterprise repositories/services overridden to share one `fakeredis`
instance, so the whole flow (bootstrap -> authenticate -> RBAC -> audit)
runs end to end without a real Redis or any real model.
"""

from collections.abc import Iterator

import pytest
from fakeredis import aioredis as fake_aioredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.enterprise import (
    get_api_key_repository,
    get_audit_repository,
    get_authentication_service,
    get_organization_repository,
    get_quota_repository,
)
from app.repositories.api_key_repository import ApiKeyRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.quota_repository import QuotaRepository
from app.services.enterprise.authentication_service import AuthenticationService

_PREFIX = settings.application.api_prefix
_ORGS_URL = f"{_PREFIX}/organizations"
_KEYS_URL = f"{_PREFIX}/api-keys"


@pytest.fixture
def enterprise_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings.enterprise, "enabled", True)
    # Disable quotas so the bootstrap/admin flow isn't throttled in tests.
    monkeypatch.setattr(settings.enterprise, "daily_request_quota", 0)
    monkeypatch.setattr(settings.enterprise, "rate_limit_per_minute", 0)

    client = fake_aioredis.FakeRedis(decode_responses=True)
    org_repo = OrganizationRepository(redis_client=client)
    key_repo = ApiKeyRepository(redis_client=client)
    audit_repo = AuditRepository(redis_client=client)
    quota_repo = QuotaRepository(redis_client=client)
    auth_service = AuthenticationService(api_key_repository=key_repo)

    app: FastAPI = create_app()
    app.dependency_overrides[get_organization_repository] = lambda: org_repo
    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_audit_repository] = lambda: audit_repo
    app.dependency_overrides[get_quota_repository] = lambda: quota_repo
    app.dependency_overrides[get_authentication_service] = lambda: auth_service
    with TestClient(app) as test_client:
        yield test_client


def _bootstrap(client: TestClient) -> str:
    """Bootstrap an org and return its owner key."""
    response = client.post(_ORGS_URL, json={"name": "Acme"})
    assert response.status_code == 201
    key: str = response.json()["api_key"]["key"]
    return key


def _headers(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


class TestBootstrap:
    def test_creates_org_tenant_and_owner_key(self, enterprise_client: TestClient) -> None:
        response = enterprise_client.post(_ORGS_URL, json={"name": "Acme"})

        assert response.status_code == 201
        body = response.json()
        assert body["organization"]["name"] == "Acme"
        assert body["tenant"]["name"] == "default"
        assert body["api_key"]["api_key"]["role"] == "owner"
        assert body["api_key"]["key"].startswith("pik_")

    def test_is_open_no_key_required(self, enterprise_client: TestClient) -> None:
        # No X-API-Key header, yet it succeeds (bootstrap).
        assert enterprise_client.post(_ORGS_URL, json={"name": "Acme"}).status_code == 201


class TestAuthGating:
    def test_list_organizations_requires_a_key(self, enterprise_client: TestClient) -> None:
        assert enterprise_client.get(_ORGS_URL).status_code == 401

    def test_owner_can_list_organizations(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)

        response = enterprise_client.get(_ORGS_URL, headers=_headers(owner_key))

        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestApiKeys:
    def test_owner_creates_a_member_key(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)

        response = enterprise_client.post(
            _KEYS_URL, json={"name": "ci", "role": "member"}, headers=_headers(owner_key)
        )

        assert response.status_code == 201
        assert response.json()["api_key"]["role"] == "member"
        # The new member key works for read but not for managing keys.
        member_key = response.json()["key"]
        assert enterprise_client.get(_KEYS_URL, headers=_headers(member_key)).status_code == 403

    def test_no_privilege_escalation(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)
        admin = enterprise_client.post(
            _KEYS_URL, json={"name": "admin", "role": "admin"}, headers=_headers(owner_key)
        ).json()["key"]

        # An admin cannot mint an owner key.
        response = enterprise_client.post(
            _KEYS_URL, json={"name": "escalate", "role": "owner"}, headers=_headers(admin)
        )

        assert response.status_code == 403

    def test_list_and_revoke(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)
        created = enterprise_client.post(
            _KEYS_URL, json={"name": "ci", "role": "member"}, headers=_headers(owner_key)
        ).json()
        prefix = created["api_key"]["prefix"]

        listed = enterprise_client.get(_KEYS_URL, headers=_headers(owner_key)).json()
        assert any(k["prefix"] == prefix for k in listed)
        assert "key" not in str(listed)  # no raw secret in a listing

        revoke = enterprise_client.delete(f"{_KEYS_URL}/{prefix}", headers=_headers(owner_key))
        assert revoke.status_code == 200
        assert revoke.json()["revoked"] is True
        # The revoked key no longer authenticates.
        assert enterprise_client.get(_KEYS_URL, headers=_headers(created["key"])).status_code == 401

    def test_revoke_unknown_key_404s(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)

        response = enterprise_client.delete(f"{_KEYS_URL}/pik_nope", headers=_headers(owner_key))

        assert response.status_code == 404


class TestAuditAndUsage:
    def test_key_actions_are_audited(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)
        enterprise_client.post(
            _KEYS_URL, json={"name": "ci", "role": "member"}, headers=_headers(owner_key)
        )

        audit = enterprise_client.get(f"{_PREFIX}/audit", headers=_headers(owner_key))

        assert audit.status_code == 200
        actions = [e["action"] for e in audit.json()]
        assert "create_api_key" in actions

    def test_usage_reports_the_tenant_quota(self, enterprise_client: TestClient) -> None:
        owner_key = _bootstrap(enterprise_client)

        usage = enterprise_client.get(f"{_PREFIX}/usage", headers=_headers(owner_key))

        assert usage.status_code == 200
        body = usage.json()
        assert "requests_today" in body
        assert "daily_request_quota" in body


class TestEnterpriseDisabled:
    def test_routes_absent_when_enterprise_disabled(self) -> None:
        # Default settings have enterprise off, so the router isn't registered.
        app = create_app()
        with TestClient(app) as client:
            assert client.post(_ORGS_URL, json={"name": "Acme"}).status_code == 404
