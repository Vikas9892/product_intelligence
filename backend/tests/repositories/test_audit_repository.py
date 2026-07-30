"""Unit tests for `AuditRepository` (fakeredis-backed)."""

from uuid import uuid4

import pytest
from fakeredis import aioredis as fake_aioredis

from app.models.audit_event import AuditEvent
from app.repositories import audit_repository
from app.repositories.audit_repository import AuditRepository


def _repo() -> AuditRepository:
    return AuditRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))


class TestAuditRepository:
    async def test_append_and_list_newest_first(self) -> None:
        repo = _repo()
        tenant_id = uuid4()
        await repo.append(AuditEvent(tenant_id=tenant_id, actor="pik_a", action="first"))
        await repo.append(AuditEvent(tenant_id=tenant_id, actor="pik_a", action="second"))

        events = await repo.list_for_tenant(tenant_id)

        assert [e.action for e in events] == ["second", "first"]

    async def test_events_are_per_tenant(self) -> None:
        repo = _repo()
        a, b = uuid4(), uuid4()
        await repo.append(AuditEvent(tenant_id=a, actor="x", action="a_action"))
        await repo.append(AuditEvent(tenant_id=b, actor="x", action="b_action"))

        assert [e.action for e in await repo.list_for_tenant(a)] == ["a_action"]
        assert [e.action for e in await repo.list_for_tenant(b)] == ["b_action"]

    async def test_trims_to_the_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audit_repository, "MAX_EVENTS_PER_TENANT", 3)
        repo = _repo()
        tenant_id = uuid4()
        for i in range(5):
            await repo.append(AuditEvent(tenant_id=tenant_id, actor="x", action=f"a{i}"))

        events = await repo.list_for_tenant(tenant_id, limit=100)

        # Only the 3 most recent are kept.
        assert [e.action for e in events] == ["a4", "a3", "a2"]

    async def test_list_respects_the_limit(self) -> None:
        repo = _repo()
        tenant_id = uuid4()
        for i in range(5):
            await repo.append(AuditEvent(tenant_id=tenant_id, actor="x", action=f"a{i}"))

        assert len(await repo.list_for_tenant(tenant_id, limit=2)) == 2
