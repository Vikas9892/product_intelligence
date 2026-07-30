"""`AuditRepository`: Redis-backed, append-only audit log (Phase 19).

Stores `AuditEvent`s in a per-tenant Redis list, newest first (`LPUSH`),
capped at `MAX_EVENTS_PER_TENANT` so the log can't grow unbounded
(`LTRIM`). No database — Redis-only, like every enterprise store. The
audit trail is security-relevant, so `append` surfaces Redis failures
rather than fail-soft: a lost audit entry should be visible, not silent.
"""

from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger
from app.models.audit_event import AuditEvent

logger = get_logger(__name__)

#: Most recent events retained per tenant (older ones are trimmed away).
MAX_EVENTS_PER_TENANT = 1000


class AuditRepository:
    """Appends and reads per-tenant audit events."""

    def __init__(self, *, redis_client: redis.Redis | None = None) -> None:
        self._redis: redis.Redis = (
            redis_client
            if redis_client is not None
            else redis.from_url(settings.async_pipeline.redis_url, decode_responses=True)
        )

    async def append(self, event: AuditEvent) -> None:
        """Append `event` to its tenant's audit log (newest first), trimming to the cap."""
        key = _audit_key(event.tenant_id)
        await self._redis.lpush(key, event.model_dump_json())
        await self._redis.ltrim(key, 0, MAX_EVENTS_PER_TENANT - 1)
        logger.info(
            "Audit event recorded: tenant_id=%s, action=%s, actor=%s",
            event.tenant_id,
            event.action,
            event.actor,
        )

    async def list_for_tenant(self, tenant_id: UUID, *, limit: int = 100) -> list[AuditEvent]:
        """Return the most recent `limit` audit events for `tenant_id`, newest first."""
        raw_events = await self._redis.lrange(_audit_key(tenant_id), 0, limit - 1)
        return [AuditEvent.model_validate_json(raw) for raw in raw_events]


def _audit_key(tenant_id: UUID) -> str:
    return f"tenant:{tenant_id}:audit"
