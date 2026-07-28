"""`RecommendationCacheRepository`: a Redis-backed cache for precomputed recommendations (Phase 12).

The worker pipeline's "Recommendation Cache" stage: after `ProductWorker`
successfully processes a product (image processing, embeddings, catalog
intelligence, vector indexing, duplicate detection all already done via
`ProductService.process_upload`), it also calls
`RecommendationEngineService.recommend` once and stores the result here
— so the *first* `GET /products/{id}/recommendations` a client makes
doesn't have to wait for that computation, only every subsequent one
until the cache entry expires (`RECOMMENDATION__CACHE_TTL_SECONDS`).

Deliberately just a `get`/`set` pair, no invalidation strategy beyond a
TTL — the diagram's own "Recommendation Cache" box is a warm-up
optimization, not a strict consistency guarantee (a product's
recommendations legitimately drift slowly as the rest of the catalog
changes, so a bounded staleness window is an acceptable trade-off,
matching how every other cache in this class of system works).
"""

from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.models.recommendation_result import RecommendationResult


class RecommendationCacheRepository:
    """Caches one `RecommendationResult` per product, keyed by product ID."""

    def __init__(
        self,
        *,
        redis_client: redis.Redis | None = None,
        ttl_seconds: float | None = None,
    ) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )
        self._ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else settings.recommendation.cache_ttl_seconds
        )

    async def get(self, product_id: UUID) -> RecommendationResult | None:
        """Return the cached recommendations for `product_id`, or `None` if absent/expired."""
        raw = await self._redis.get(self._key(product_id))
        return RecommendationResult.model_validate_json(raw) if raw is not None else None

    async def set(self, product_id: UUID, result: RecommendationResult) -> None:
        """Cache `result` for `product_id`, expiring after this repository's configured TTL."""
        await self._redis.set(
            self._key(product_id), result.model_dump_json(), ex=int(self._ttl_seconds)
        )

    def _key(self, product_id: UUID) -> str:
        return f"recommendation_cache:{product_id}"
