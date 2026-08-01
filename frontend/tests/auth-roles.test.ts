import { describe, expect, it } from "vitest";

import {
  ENDPOINT_PERMISSION,
  ROLE_PERMISSIONS,
  ROLES,
  can,
  canAssignRole,
  isRole,
  roleAtLeast,
  roleHasPermission,
  type Role,
  type UiCapability,
} from "@/lib/auth/roles";

/**
 * The authoritative matrix, observed against the running backend by calling
 * each endpoint with a real key of each role:
 *
 *                  owner  admin  member  viewer
 *  /organizations   200    403     403     403
 *  /api-keys        200    200     403     403
 *  /audit           200    200     403     403
 *  /usage           200    200     403     403
 *
 * `can()` must agree with this exactly — anywhere it says `true` and the
 * backend says 403, the UI leads a user into a dead end.
 */
const OBSERVED: Record<UiCapability, Record<Role, boolean>> = {
  manageOrganization: { owner: true, admin: false, member: false, viewer: false },
  manageApiKeys: { owner: true, admin: true, member: false, viewer: false },
  viewAudit: { owner: true, admin: true, member: false, viewer: false },
  viewUsage: { owner: true, admin: true, member: false, viewer: false },
};

describe("ROLE_PERMISSIONS", () => {
  it("transcribes the backend's mapping exactly", () => {
    expect(ROLE_PERMISSIONS.viewer).toEqual(["read"]);
    expect(ROLE_PERMISSIONS.member).toEqual(["read", "write"]);
    expect(ROLE_PERMISSIONS.admin).toEqual([
      "read",
      "write",
      "manage_api_keys",
      "view_audit",
      "view_usage",
    ]);
    expect(ROLE_PERMISSIONS.owner).toContain("manage_organization");
  });

  it("grants manage_organization to owner alone", () => {
    expect(roleHasPermission("owner", "manage_organization")).toBe(true);
    expect(roleHasPermission("admin", "manage_organization")).toBe(false);
  });

  it("first grants the enterprise-management permissions at admin", () => {
    // The distinction that the previous minimum-role model got wrong.
    for (const permission of ["manage_api_keys", "view_audit", "view_usage"] as const) {
      expect(roleHasPermission("member", permission)).toBe(false);
      expect(roleHasPermission("admin", permission)).toBe(true);
    }
  });

  it("is null-safe", () => {
    expect(roleHasPermission(null, "read")).toBe(false);
    expect(roleHasPermission(undefined, "read")).toBe(false);
  });
});

describe("can", () => {
  it.each(Object.keys(OBSERVED) as UiCapability[])(
    "matches the backend for %s across every role",
    (capability) => {
      for (const role of ROLES) {
        expect(can(role, capability)).toBe(OBSERVED[capability][role]);
      }
    },
  );

  it("does not grant usage to a member", () => {
    // Regression: this previously returned true because `viewUsage` was
    // modelled as minimum-role "member". The backend answers 403, so a member
    // was shown a usage panel that could never load.
    expect(can("member", "viewUsage")).toBe(false);
  });

  it("grants nothing without a role", () => {
    for (const capability of Object.keys(OBSERVED) as UiCapability[]) {
      expect(can(null, capability)).toBe(false);
    }
  });
});

describe("ENDPOINT_PERMISSION", () => {
  it("names the permission each route requires", () => {
    expect(ENDPOINT_PERMISSION.manageOrganization).toBe("manage_organization");
    expect(ENDPOINT_PERMISSION.manageApiKeys).toBe("manage_api_keys");
    expect(ENDPOINT_PERMISSION.viewAudit).toBe("view_audit");
    expect(ENDPOINT_PERMISSION.viewUsage).toBe("view_usage");
  });
});

describe("canAssignRole", () => {
  it("lets a role mint its own level and below, but not above", () => {
    // Matches the backend's subset check, which refused admin -> owner with
    // "Role 'admin' cannot create a key with the higher role 'owner'."
    expect(canAssignRole("admin", "owner")).toBe(false);
    expect(canAssignRole("admin", "admin")).toBe(true);
    expect(canAssignRole("admin", "member")).toBe(true);
    expect(canAssignRole("owner", "owner")).toBe(true);
    expect(canAssignRole(null, "viewer")).toBe(false);
  });
});

describe("roleAtLeast", () => {
  it("is cumulative and null-safe", () => {
    expect(roleAtLeast("owner", "admin")).toBe(true);
    expect(roleAtLeast("admin", "admin")).toBe(true);
    expect(roleAtLeast("viewer", "member")).toBe(false);
    expect(roleAtLeast(null, "viewer")).toBe(false);
  });
});

describe("isRole", () => {
  it("narrows correctly", () => {
    expect(isRole("owner")).toBe(true);
    expect(isRole("nope")).toBe(false);
    expect(isRole(42)).toBe(false);
  });
});
