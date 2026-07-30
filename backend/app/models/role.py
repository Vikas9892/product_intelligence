"""Internal domain model: `Role` and `Permission`, the RBAC vocabulary (Phase 19).

The role-based access-control primitives for the opt-in enterprise layer.
`Permission` is the fine-grained capability an endpoint requires; `Role`
is the coarse label attached to an API key; `ROLE_PERMISSIONS` maps each
role to the permissions it grants. A route asks for a `Permission` (via
the `require_permission` dependency, Milestone 2); the authenticated key's
`Role` either grants it or the request is `403`ed.

Roles are cumulative, widest first: `OWNER` ⊇ `ADMIN` ⊇ `MEMBER` ⊇
`VIEWER`. Kept as explicit per-role permission sets (rather than an
inheritance chain) so exactly what each role can do is readable in one
place.
"""

from enum import StrEnum


class Permission(StrEnum):
    """One fine-grained capability an enterprise endpoint can require."""

    #: Create/list organizations and tenants.
    MANAGE_ORGANIZATION = "manage_organization"
    #: Create/revoke API keys.
    MANAGE_API_KEYS = "manage_api_keys"
    #: Read the audit log.
    VIEW_AUDIT = "view_audit"
    #: Read usage/quota.
    VIEW_USAGE = "view_usage"
    #: Mutating business actions (upload, check-duplicate).
    WRITE = "write"
    #: Read-only business actions (search, recommendations, pricing, analytics).
    READ = "read"


class Role(StrEnum):
    """The role attached to an API key, granting a fixed set of permissions."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


#: What each role is allowed to do — cumulative from VIEWER up to OWNER.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ}),
    Role.MEMBER: frozenset({Permission.READ, Permission.WRITE}),
    Role.ADMIN: frozenset(
        {
            Permission.READ,
            Permission.WRITE,
            Permission.MANAGE_API_KEYS,
            Permission.VIEW_AUDIT,
            Permission.VIEW_USAGE,
        }
    ),
    Role.OWNER: frozenset(Permission),
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Return whether `role` grants `permission`."""
    return permission in ROLE_PERMISSIONS[role]
