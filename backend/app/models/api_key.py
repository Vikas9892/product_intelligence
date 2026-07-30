"""Internal domain models: `ApiKey` and `ApiKeyCreation` (Phase 19).

`ApiKey` is the *stored* record — it never holds the raw secret, only a
salted hash of it plus a short non-secret `prefix` used to look the record
up quickly. `ApiKeyCreation` is returned *once*, at creation time, and is
the only moment the raw `key` is ever available: a caller must save it
then, because it can't be recovered afterward (only its hash is stored),
the same one-time-reveal contract every real API-key system uses.

Persisted as JSON in Redis by `ApiKeyRepository` (Milestone 2).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.models.role import Role


class ApiKey(BaseModel):
    """A stored API-key record — hash + metadata, never the raw secret."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=200)
    role: Role
    #: Short, non-secret leading segment of the raw key, used as the lookup
    #: index (`prefix -> record`) so verifying a key is one Redis GET.
    prefix: str = Field(min_length=1)
    #: Salted hash of the full raw key — what a presented key is checked against.
    key_hash: str = Field(min_length=1)
    revoked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApiKeyCreation(BaseModel):
    """A newly-created key: the stored record plus the raw secret, shown only once."""

    api_key: ApiKey
    #: The raw secret — available only in this response, never stored or recoverable.
    key: str
