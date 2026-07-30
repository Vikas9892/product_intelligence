"""Internal domain model: `AuditEvent`, one recorded enterprise action (Phase 19).

An append-only record of who did what, when, per tenant — the audit
trail the enterprise layer keeps for security/compliance. `actor` is the
API key's `prefix` (non-secret, identifies the key without exposing it);
`action`/`resource` describe what happened; `metadata` carries small
structured context. Persisted per tenant in Redis by `AuditRepository`
(Milestone 4). Never carries a raw API key, embedding, or product payload.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """One append-only audit-log entry."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    actor: str
    action: str
    resource: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
