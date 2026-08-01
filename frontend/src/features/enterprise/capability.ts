import { ApiError } from "@/lib/api";

/**
 * What the backend's enterprise layer is actually doing right now.
 *
 * Derived from real behavior rather than a build-time flag, because the backend
 * only mounts the enterprise router when `ENTERPRISE__ENABLED` is on
 * (`app/application.py`). That makes the HTTP status of any enterprise route a
 * reliable, three-way signal:
 *
 * | Status | Meaning                                                        |
 * |--------|----------------------------------------------------------------|
 * | 404    | router not mounted — the layer is **disabled**                 |
 * | 401    | mounted, but the key is missing or invalid                     |
 * | 403    | mounted, key is **valid**, role lacks this specific permission |
 * | 200    | mounted, authenticated, and permitted                          |
 *
 * The 403 case matters: it still proves enterprise is enabled *and* the key
 * authenticated, so it must not be read as "unavailable".
 */
export type EnterpriseCapability = "disabled" | "unauthenticated" | "authenticated" | "unknown";

/** The probe's outcome, plus whether the probed permission was granted. */
export interface CapabilityProbeResult {
  capability: EnterpriseCapability;
  /**
   * True only for a 200. A 403 means authenticated-but-not-permitted, which is
   * a successful capability probe and an unsuccessful permission check.
   */
  permitted: boolean;
  /** The status the probe observed, for diagnostics. */
  status: number | null;
}

/**
 * Maps a thrown error (or a success) from an enterprise route onto a
 * capability. Pure, so the mapping is testable without a network.
 */
export function capabilityFromError(error: unknown): CapabilityProbeResult {
  if (!(error instanceof ApiError)) {
    return { capability: "unknown", permitted: false, status: null };
  }
  switch (error.status) {
    case 404:
      return { capability: "disabled", permitted: false, status: 404 };
    case 401:
      return { capability: "unauthenticated", permitted: false, status: 401 };
    case 403:
      // Enterprise is on and the key is valid — the role just lacks this one
      // permission. Still "authenticated".
      return { capability: "authenticated", permitted: false, status: 403 };
    default:
      // A network failure or 5xx tells us nothing about the feature flag.
      return { capability: "unknown", permitted: false, status: error.status };
  }
}

/** The successful counterpart of {@link capabilityFromError}. */
export function capabilityFromSuccess(): CapabilityProbeResult {
  return { capability: "authenticated", permitted: true, status: 200 };
}

/** Whether the enterprise surface should be offered at all. */
export function isEnterpriseAvailable(capability: EnterpriseCapability): boolean {
  return capability === "unauthenticated" || capability === "authenticated";
}

/** Human copy for each capability state. */
export const CAPABILITY_COPY: Record<EnterpriseCapability, { title: string; description: string }> =
  {
    disabled: {
      title: "Enterprise layer is disabled",
      description:
        "The backend is running single-tenant with ENTERPRISE__ENABLED off, so the organization, API-key, audit, and usage routes are not mounted. Every other feature works without authentication — this is the default demo configuration.",
    },
    unauthenticated: {
      title: "Enterprise layer is enabled",
      description:
        "The backend has the enterprise routes mounted but this session has no valid API key. Bootstrap an organization or paste an existing key to continue.",
    },
    authenticated: {
      title: "Signed in",
      description: "This session holds a valid API key for the tenant shown below.",
    },
    unknown: {
      title: "Enterprise state unknown",
      description:
        "The backend could not be reached, so whether the enterprise layer is enabled cannot be determined. This is a connectivity problem, not a configuration one.",
    },
  };
