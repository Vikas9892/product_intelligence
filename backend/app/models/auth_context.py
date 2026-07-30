"""Internal domain model: `AuthContext`, the resolved identity of a request (Phase 19).

What `AuthenticationService` produces from a valid API key: which
organization and tenant the request acts as, the key's role (for RBAC),
and the key's id/prefix (for audit logging). Carried through the request
(via the `require_permission` dependency) so tenant-scoped resources and
audit entries can be derived from it. Never carries the raw key.
"""

from uuid import UUID

from pydantic import BaseModel

from app.models.role import Role


class AuthContext(BaseModel):
    """The authenticated identity behind one enterprise request."""

    organization_id: UUID
    tenant_id: UUID
    role: Role
    api_key_id: UUID
    api_key_prefix: str
