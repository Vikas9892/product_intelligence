"""Internal domain models: `Organization` and `Tenant` (Phase 19).

The top-level account (`Organization`) and its isolation boundary
(`Tenant`). A tenant belongs to exactly one organization; `tenant.id` is
the key everything tenant-scoped (Qdrant collections, analytics/quota
buckets, audit log) partitions on. An organization gets one default
tenant on creation, but the model allows more (e.g. prod/staging
environments under one account).

Persisted as JSON in Redis by `OrganizationRepository` (Milestone 2) —
no database, matching this project's Redis-only persistence.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Organization(BaseModel):
    """A top-level enterprise account."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Tenant(BaseModel):
    """An isolation boundary within an organization — the unit everything scopes on."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    name: str = Field(min_length=1, max_length=200)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
