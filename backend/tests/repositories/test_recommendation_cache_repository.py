"""Unit tests for `RecommendationCacheRepository`.

Uses `fakeredis`'s async client — see `tests/queue/test_redis_queue.py`'s
own docstring for why.
"""

from uuid import uuid4

from fakeredis import aioredis as fake_aioredis

from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType
from app.repositories.recommendation_cache_repository import RecommendationCacheRepository


def _repository(*, ttl_seconds: float = 3600.0) -> RecommendationCacheRepository:
    client = fake_aioredis.FakeRedis(decode_responses=True)
    return RecommendationCacheRepository(redis_client=client, ttl_seconds=ttl_seconds)


def _result() -> RecommendationResult:
    return RecommendationResult(
        recommendations=[
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.9,
                quality_score=0.8,
                final_score=0.85,
                reason=RecommendationReason(),
            )
        ],
        processing_time=0.01,
        recommendation_type=RecommendationType.SIMILAR,
    )


class TestRecommendationCacheRepository:
    async def test_get_returns_none_when_uncached(self) -> None:
        repository = _repository()

        assert await repository.get(uuid4()) is None

    async def test_set_then_get_round_trips(self) -> None:
        repository = _repository()
        product_id = uuid4()
        result = _result()

        await repository.set(product_id, result)
        cached = await repository.get(product_id)

        assert cached == result

    async def test_entries_are_cached_per_product_id(self) -> None:
        repository = _repository()
        first_id, second_id = uuid4(), uuid4()
        first_result, second_result = _result(), _result()

        await repository.set(first_id, first_result)
        await repository.set(second_id, second_result)

        assert await repository.get(first_id) == first_result
        assert await repository.get(second_id) == second_result

    async def test_entries_expire_after_the_configured_ttl(self) -> None:
        repository = _repository(ttl_seconds=1)
        product_id = uuid4()

        await repository.set(product_id, _result())

        stored_ttl = await repository._redis.ttl(repository._key(product_id))
        assert 0 < stored_ttl <= 1
