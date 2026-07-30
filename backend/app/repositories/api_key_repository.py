"""`ApiKeyRepository`: Redis-backed API-key records (Phase 19).

Persists `ApiKey` records (hash + metadata, never the raw secret) as JSON
in Redis, indexed by their non-secret `prefix` so verifying a presented
key is a single lookup. Also tracks each tenant's key prefixes so an
admin can list/revoke them. No database — Redis-only, like every other
enterprise store.
"""

from typing import cast
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.models.api_key import ApiKey

logger = get_logger(__name__)


class ApiKeyRepository:
    """Stores and retrieves API-key records, indexed by prefix."""

    def __init__(self, *, redis_client: redis.Redis | None = None) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )

    async def create(self, api_key: ApiKey) -> ApiKey:
        """Persist `api_key`, indexed by its prefix and its tenant."""
        await self._save(api_key)
        await self._redis.sadd(_tenant_keys_key(api_key.tenant_id), api_key.prefix)
        logger.info(
            "API key created: prefix=%s, tenant_id=%s, role=%s",
            api_key.prefix,
            api_key.tenant_id,
            api_key.role.value,
        )
        return api_key

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        """Return the API-key record for `prefix`, or `None`."""
        raw = await self._redis.get(_prefix_key(prefix))
        return ApiKey.model_validate_json(raw) if raw is not None else None

    async def list_by_tenant(self, tenant_id: UUID) -> list[ApiKey]:
        """Return every API-key record for `tenant_id`."""
        prefixes = await self._redis.smembers(_tenant_keys_key(tenant_id))
        keys: list[ApiKey] = []
        for prefix in prefixes:
            key = await self.get_by_prefix(cast(str, prefix))
            if key is not None:
                keys.append(key)
        return keys

    async def revoke(self, prefix: str) -> ApiKey | None:
        """Mark the key with `prefix` revoked, returning the updated record (or `None`)."""
        api_key = await self.get_by_prefix(prefix)
        if api_key is None:
            return None
        revoked = api_key.model_copy(update={"revoked": True})
        await self._save(revoked)
        logger.info("API key revoked: prefix=%s", prefix)
        return revoked

    async def _save(self, api_key: ApiKey) -> None:
        await self._redis.set(_prefix_key(api_key.prefix), api_key.model_dump_json())


def _prefix_key(prefix: str) -> str:
    return f"apikey:prefix:{prefix}"


def _tenant_keys_key(tenant_id: UUID) -> str:
    return f"tenant:{tenant_id}:apikeys"
