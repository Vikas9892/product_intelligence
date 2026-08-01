/**
 * Client-side mirror of the backend's RBAC vocabulary.
 *
 * This file is a **transcription of `backend/app/models/role.py`**, not an
 * interpretation of it. `Permission`, `Role`, and `ROLE_PERMISSIONS` below use
 * the same names and the same mapping the server uses, so the two can be
 * diffed directly.
 *
 * Its only job is to reduce dead ends in the UI — hiding or disabling actions
 * the current key demonstrably cannot perform. It is **never** an authorization
 * decision: the server's 401/403 is the security boundary, every gated call is
 * still made against it, and a denial is surfaced rather than assumed.
 */

/** One fine-grained capability an enterprise endpoint can require. */
export type Permission =
  "manage_organization" | "manage_api_keys" | "view_audit" | "view_usage" | "write" | "read";

/** The role attached to an API key. */
export type Role = "owner" | "admin" | "member" | "viewer";

/** Least to most privileged. Used for ordering UI, not for deciding access. */
export const ROLES: readonly Role[] = ["viewer", "member", "admin", "owner"] as const;

/**
 * What each role grants — transcribed from the backend's `ROLE_PERMISSIONS`.
 *
 * Note this is **not** a simple rank ladder: `member` adds `write` to `viewer`,
 * but every enterprise-management permission appears first at `admin`, and
 * `manage_organization` only at `owner`. Modelling it as a rank comparison is
 * exactly what produced the bug this file replaces (see `can` below), so the
 * mapping is kept explicit.
 */
export const ROLE_PERMISSIONS: Record<Role, readonly Permission[]> = {
  viewer: ["read"],
  member: ["read", "write"],
  admin: ["read", "write", "manage_api_keys", "view_audit", "view_usage"],
  owner: ["read", "write", "manage_api_keys", "view_audit", "view_usage", "manage_organization"],
};

/** Whether `role` grants `permission`. Mirrors the backend's `role_has_permission`. */
export function roleHasPermission(role: Role | null | undefined, permission: Permission): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role].includes(permission);
}

const RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

/**
 * True when `role` is at least as privileged as `minimum`.
 *
 * Retained for ordering concerns (such as which role may mint which key). Do
 * **not** use it to decide whether an endpoint is callable — use
 * {@link roleHasPermission}, because privilege rank and permission grants are
 * not the same thing.
 */
export function roleAtLeast(role: Role | null | undefined, minimum: Role): boolean {
  if (!role) return false;
  return RANK[role] >= RANK[minimum];
}

/**
 * Whether `actor` may create a key with role `target`.
 *
 * The backend refuses when the target's permission set is not a subset of the
 * caller's. Under the real mapping that coincides with a rank comparison, so
 * this is a faithful hint — but the server still decides, and its 403 is shown.
 */
export function canAssignRole(actor: Role | null | undefined, target: Role): boolean {
  return roleAtLeast(actor, target);
}

/** Narrowing guard for values that should be a `Role`. */
export function isRole(value: unknown): value is Role {
  return typeof value === "string" && value in RANK;
}

/**
 * The permission each enterprise endpoint requires, transcribed from the route
 * definitions in `backend/app/api/enterprise.py`.
 *
 * Confirmed against the running backend — observed status by role:
 *
 * |                | owner | admin | member | viewer |
 * |----------------|-------|-------|--------|--------|
 * | /organizations | 200   | 403   | 403    | 403    |
 * | /api-keys      | 200   | 200   | 403    | 403    |
 * | /audit         | 200   | 200   | 403    | 403    |
 * | /usage         | 200   | 200   | 403    | 403    |
 */
export const ENDPOINT_PERMISSION = {
  manageOrganization: "manage_organization",
  manageApiKeys: "manage_api_keys",
  viewAudit: "view_audit",
  viewUsage: "view_usage",
} as const satisfies Record<string, Permission>;

export type UiCapability = keyof typeof ENDPOINT_PERMISSION;

/**
 * Whether the given role may perform a UI capability (a hint only).
 *
 * This previously used a minimum-role table that listed `viewUsage` as
 * `member`. That was wrong: `VIEW_USAGE` first appears at `admin`, so a member
 * saw the usage UI enabled and then hit a 403. Deriving from the permission map
 * removes that class of drift entirely.
 */
export function can(role: Role | null | undefined, capability: UiCapability): boolean {
  return roleHasPermission(role, ENDPOINT_PERMISSION[capability]);
}
