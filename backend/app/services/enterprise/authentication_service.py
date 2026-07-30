"""`AuthenticationService`: resolves a raw API key into an `AuthContext` (Phase 19).

The single seam that turns "an `X-API-Key` header value" into "who this
request acts as." Given a raw key, it looks up the stored record by
prefix, rejects a missing/unknown/revoked key or one whose hash doesn't
match (`AuthenticationException`, 401), and otherwise returns the
`AuthContext` (organization, tenant, role, key id/prefix) the rest of the
request scopes and audits on. Constant-time hash comparison
(`api_keys.verify_key`) keeps a wrong key from leaking timing.

Also creates API keys: it generates the raw secret (returned once via
`ApiKeyCreation`), stores only its hash, and never logs the secret.
"""

from uuid import UUID

from app.core.logging import get_logger
from app.exceptions.errors import AuthenticationException
from app.models.api_key import ApiKey, ApiKeyCreation
from app.models.auth_context import AuthContext
from app.models.role import Role
from app.repositories.api_key_repository import ApiKeyRepository
from app.services.enterprise import api_keys

logger = get_logger(__name__)


class AuthenticationService:
    """Authenticates API keys and issues new ones."""

    def __init__(self, *, api_key_repository: ApiKeyRepository | None = None) -> None:
        self._api_key_repository = (
            api_key_repository if api_key_repository is not None else ApiKeyRepository()
        )

    async def authenticate(self, raw_key: str | None) -> AuthContext:
        """Resolve `raw_key` into an `AuthContext`, or raise `AuthenticationException` (401)."""
        if not raw_key:
            raise AuthenticationException("No API key was provided.")
        record = await self._api_key_repository.get_by_prefix(api_keys.key_prefix(raw_key))
        if record is None or record.revoked:
            raise AuthenticationException("The API key is invalid or has been revoked.")
        if not api_keys.verify_key(raw_key, record.key_hash):
            raise AuthenticationException("The API key is invalid or has been revoked.")
        return AuthContext(
            organization_id=record.organization_id,
            tenant_id=record.tenant_id,
            role=record.role,
            api_key_id=record.id,
            api_key_prefix=record.prefix,
        )

    async def create_api_key(
        self, *, organization_id: UUID, tenant_id: UUID, name: str, role: Role
    ) -> ApiKeyCreation:
        """Create a new API key, returning the raw secret exactly once."""
        raw_key = api_keys.generate_raw_key()
        record = ApiKey(
            organization_id=organization_id,
            tenant_id=tenant_id,
            name=name,
            role=role,
            prefix=api_keys.key_prefix(raw_key),
            key_hash=api_keys.hash_key(raw_key),
        )
        await self._api_key_repository.create(record)
        return ApiKeyCreation(api_key=record, key=raw_key)
