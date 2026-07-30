"""`TenantScope`: derives tenant-isolated resource names from a tenant (Phase 19).

The isolation *mechanism* the opt-in enterprise layer provides, without
rewriting any Phase 2-18 service. Given a tenant (or an `AuthContext`),
it produces the tenant-scoped names those resources would use under
multi-tenancy:

- **Qdrant collections** — `{collection_prefix}_{tenant_id}_{base}`, so
  each tenant's vectors live in physically separate collections a query
  can't cross into.
- **Redis namespaces** — `tenant:{tenant_id}:{...}`, the prefix
  tenant-scoped analytics/quota/audit keys hang off, so one tenant's
  counters never collide with another's.

An enterprise-aware caller builds a `TenantScope` from the request's
`AuthContext` and constructs its tenant's `QdrantVectorStore` /
repositories with these names. Existing single-tenant callers keep using
the unscoped defaults, so nothing built before Phase 19 changes. Pure and
deterministic — same tenant, same names.
"""

from uuid import UUID

from app.core.config import settings
from app.models.auth_context import AuthContext


class TenantScope:
    """Produces tenant-isolated Qdrant collection names and Redis key namespaces."""

    def __init__(self, tenant_id: UUID, *, collection_prefix: str | None = None) -> None:
        self._tenant_id = tenant_id
        self._collection_prefix = (
            collection_prefix
            if collection_prefix is not None
            else settings.enterprise.collection_prefix
        )

    @classmethod
    def from_auth(cls, context: AuthContext) -> "TenantScope":
        """Build a `TenantScope` for the tenant behind an authenticated request."""
        return cls(context.tenant_id)

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    def collection_name(self, base: str) -> str:
        """Return the tenant-scoped Qdrant collection name for `base`."""
        return f"{self._collection_prefix}_{self._tenant_id}_{base}"

    def redis_namespace(self, *parts: str) -> str:
        """Return a tenant-scoped Redis key prefix, joined from `parts`."""
        suffix = ":".join(parts)
        base = f"tenant:{self._tenant_id}"
        return f"{base}:{suffix}" if suffix else base
