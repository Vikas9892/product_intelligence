/**
 * Client-side mirror of the backend's RBAC roles, used only to *hint* the UI
 * (hide/disable actions the current key can't perform). The server's `403` is
 * always the real gate — these checks never grant access, they only reduce
 * dead-ends. Roles are cumulative: viewer ⊆ member ⊆ admin ⊆ owner.
 */
export type Role = "owner" | "admin" | "member" | "viewer";

export const ROLES: readonly Role[] = ["viewer", "member", "admin", "owner"] as const;

const RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

/** True when `role` is at least as privileged as `minimum`. */
export function roleAtLeast(role: Role | null | undefined, minimum: Role): boolean {
  if (!role) return false;
  return RANK[role] >= RANK[minimum];
}

/**
 * UI capabilities keyed to the minimum role that the backend requires for the
 * corresponding action. Conservative and cumulative; used only to gate UI
 * affordances, never as an authorization decision.
 */
export const MIN_ROLE = {
  manageOrganization: "owner",
  manageApiKeys: "admin",
  viewAudit: "admin",
  viewUsage: "member",
} as const satisfies Record<string, Role>;

export type UiCapability = keyof typeof MIN_ROLE;

/** Whether the given role may perform a UI capability (hint only). */
export function can(role: Role | null | undefined, capability: UiCapability): boolean {
  return roleAtLeast(role, MIN_ROLE[capability]);
}

/** Narrowing guard for values that should be a `Role`. */
export function isRole(value: unknown): value is Role {
  return typeof value === "string" && value in RANK;
}
