import { describe, expect, it } from "vitest";

import { can, isRole, roleAtLeast } from "@/lib/auth/roles";

describe("roles", () => {
  it("roleAtLeast is cumulative and null-safe", () => {
    expect(roleAtLeast("owner", "admin")).toBe(true);
    expect(roleAtLeast("admin", "admin")).toBe(true);
    expect(roleAtLeast("viewer", "member")).toBe(false);
    expect(roleAtLeast(null, "viewer")).toBe(false);
  });

  it("can maps capabilities to their minimum role", () => {
    expect(can("owner", "manageOrganization")).toBe(true);
    expect(can("admin", "manageOrganization")).toBe(false);
    expect(can("admin", "manageApiKeys")).toBe(true);
    expect(can("member", "viewUsage")).toBe(true);
    expect(can("viewer", "viewUsage")).toBe(false);
  });

  it("isRole narrows correctly", () => {
    expect(isRole("owner")).toBe(true);
    expect(isRole("nope")).toBe(false);
    expect(isRole(42)).toBe(false);
  });
});
