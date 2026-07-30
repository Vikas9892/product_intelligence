"""Unit tests for `AnalyticsRepository` (fakeredis-backed)."""

from datetime import date

from fakeredis import aioredis as fake_aioredis

from app.models.analytics_event import AnalyticsEvent
from app.repositories.analytics_repository import AnalyticsRepository


def _repo() -> AnalyticsRepository:
    return AnalyticsRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))


_DAY = date(2026, 1, 15)


class TestRecordEvent:
    async def test_increments_the_daily_counter(self) -> None:
        repo = _repo()

        await repo.record_event(AnalyticsEvent.UPLOAD, day=_DAY)
        await repo.record_event(AnalyticsEvent.UPLOAD, day=_DAY)

        assert await repo.count_for(AnalyticsEvent.UPLOAD, _DAY) == 2

    async def test_counts_are_per_event_and_per_day(self) -> None:
        repo = _repo()

        await repo.record_event(AnalyticsEvent.UPLOAD, day=_DAY)
        await repo.record_event(AnalyticsEvent.SEARCH, day=_DAY)

        assert await repo.count_for(AnalyticsEvent.UPLOAD, _DAY) == 1
        assert await repo.count_for(AnalyticsEvent.SEARCH, _DAY) == 1
        assert await repo.count_for(AnalyticsEvent.UPLOAD, date(2026, 1, 16)) == 0


class TestDefaultDay:
    async def test_record_and_count_default_to_today(self) -> None:
        from datetime import UTC, datetime

        repo = _repo()
        today = datetime.now(UTC).date()

        await repo.record_event(AnalyticsEvent.UPLOAD)

        assert await repo.count_for(AnalyticsEvent.UPLOAD, today) == 1


class TestCountRange:
    async def test_returns_counts_for_each_day_in_order(self) -> None:
        repo = _repo()
        days = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
        await repo.record_event(AnalyticsEvent.UPLOAD, day=days[0])
        await repo.record_event(AnalyticsEvent.UPLOAD, day=days[2])
        await repo.record_event(AnalyticsEvent.UPLOAD, day=days[2])

        assert await repo.count_range(AnalyticsEvent.UPLOAD, days) == [1, 0, 2]

    async def test_empty_days_yields_empty(self) -> None:
        assert await _repo().count_range(AnalyticsEvent.UPLOAD, []) == []


class TestLatency:
    async def test_accumulates_sum_and_count(self) -> None:
        repo = _repo()

        await repo.record_latency(1.5, day=_DAY)
        await repo.record_latency(2.5, day=_DAY)

        total, count = await repo.latency_range([_DAY])
        assert total == 4.0
        assert count == 2

    async def test_empty_days_yields_zero(self) -> None:
        assert await _repo().latency_range([]) == (0.0, 0)


class TestFailSoft:
    async def test_record_event_never_raises_when_redis_is_down(self) -> None:
        class _Unreachable:
            async def incr(self, key: str) -> int:
                raise ConnectionError("down")

            async def expire(self, key: str, ttl: int) -> bool:
                raise ConnectionError("down")

        repo = AnalyticsRepository(redis_client=_Unreachable())  # type: ignore[arg-type]

        # Must not raise.
        await repo.record_event(AnalyticsEvent.UPLOAD, day=_DAY)

    async def test_record_latency_never_raises_when_redis_is_down(self) -> None:
        class _Unreachable:
            async def incrbyfloat(self, key: str, amount: float) -> float:
                raise ConnectionError("down")

        repo = AnalyticsRepository(redis_client=_Unreachable())  # type: ignore[arg-type]

        await repo.record_latency(1.0, day=_DAY)
