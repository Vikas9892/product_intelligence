import { describe, expect, it } from "vitest";

import {
  capabilityFromError,
  capabilityFromSuccess,
  isEnterpriseAvailable,
} from "@/features/enterprise/capability";
import { ApiError } from "@/lib/api";

function apiError(status: number): ApiError {
  return new ApiError("boom", { status, code: `HTTP_${status}` });
}

/**
 * These mappings were verified against the running backend:
 *   enterprise off        -> 404 on /usage, /audit, /api-keys, /organizations
 *   enterprise on, no key -> 401 on all four
 *   valid key, low role   -> 403
 *   valid key, permitted  -> 200
 */
describe("capabilityFromError", () => {
  it("treats 404 as the layer being disabled", () => {
    // The backend only mounts the enterprise router when ENTERPRISE__ENABLED
    // is on, so an unmounted route is the feature flag speaking.
    expect(capabilityFromError(apiError(404))).toEqual({
      capability: "disabled",
      permitted: false,
      status: 404,
    });
  });

  it("treats 401 as enabled but not signed in", () => {
    expect(capabilityFromError(apiError(401))).toEqual({
      capability: "unauthenticated",
      permitted: false,
      status: 401,
    });
  });

  it("treats 403 as authenticated but not permitted", () => {
    // The critical distinction: a 403 proves the router is mounted AND the key
    // authenticated. Reading it as "unavailable" would hide a working feature.
    expect(capabilityFromError(apiError(403))).toEqual({
      capability: "authenticated",
      permitted: false,
      status: 403,
    });
  });

  it("does not infer the feature flag from a network or server failure", () => {
    expect(capabilityFromError(apiError(0)).capability).toBe("unknown");
    expect(capabilityFromError(apiError(500)).capability).toBe("unknown");
    expect(capabilityFromError(new Error("not an ApiError")).capability).toBe("unknown");
  });
});

describe("capabilityFromSuccess", () => {
  it("reports authenticated and permitted", () => {
    expect(capabilityFromSuccess()).toEqual({
      capability: "authenticated",
      permitted: true,
      status: 200,
    });
  });
});

describe("isEnterpriseAvailable", () => {
  it("is true only when the router is actually mounted", () => {
    expect(isEnterpriseAvailable("authenticated")).toBe(true);
    expect(isEnterpriseAvailable("unauthenticated")).toBe(true);
    expect(isEnterpriseAvailable("disabled")).toBe(false);
    // Unknown must not enable the surface — failing open would show enterprise
    // UI that cannot work.
    expect(isEnterpriseAvailable("unknown")).toBe(false);
  });
});
