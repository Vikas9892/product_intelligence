"""Unit tests for `QuotaRepository` (fakeredis-backed)."""

from uuid import uuid4

from fakeredis import aioredis as fake_aioredis

from app.repositories.quota_repository import QuotaRepository


def _repo() -> QuotaRepository:
    return QuotaRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))


class TestQuotaRepository:
    async def test_hit_increments_daily_and_minute_counts(self) -> None:
        repo = _repo()
        tenant_id = uuid4()

        first = await repo.hit(tenant_id)
        second = await repo.hit(tenant_id)

        assert first == (1, 1)
        assert second == (2, 2)

    async def test_counts_are_per_tenant(self) -> None:
        repo = _repo()
        a, b = uuid4(), uuid4()

        await repo.hit(a)
        daily_b, _minute_b = await repo.hit(b)

        assert daily_b == 1

    async def test_usage_reads_without_incrementing(self) -> None:
        repo = _repo()
        tenant_id = uuid4()
        await repo.hit(tenant_id)
        await repo.hit(tenant_id)

        assert await repo.usage(tenant_id) == 2
        # Reading again didn't change the count.
        assert await repo.usage(tenant_id) == 2

    async def test_usage_is_zero_for_a_fresh_tenant(self) -> None:
        assert await _repo().usage(uuid4()) == 0
