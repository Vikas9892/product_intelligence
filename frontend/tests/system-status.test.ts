import { describe, expect, it } from "vitest";

import {
  overallStatus,
  queueDepthIsMeaningful,
  STATUS_LABEL,
  toStatus,
} from "@/features/system/status";

describe("toStatus", () => {
  it("maps the backend's literal health strings", () => {
    expect(toStatus("healthy")).toBe("healthy");
    expect(toStatus("unhealthy")).toBe("unhealthy");
  });

  it("treats anything else as unknown rather than guessing", () => {
    expect(toStatus(null)).toBe("unknown");
    expect(toStatus(undefined)).toBe("unknown");
    expect(toStatus("degraded")).toBe("unknown");
    expect(toStatus("")).toBe("unknown");
  });
});

describe("queueDepthIsMeaningful", () => {
  it("is false when Redis is unavailable", () => {
    // SystemHealthService degrades a failed read to 0 instead of raising, so a
    // reported depth of 0 with Redis down is a fallback, not a measurement.
    expect(queueDepthIsMeaningful("unhealthy")).toBe(false);
    expect(queueDepthIsMeaningful("unknown")).toBe(false);
  });

  it("is true only when Redis is healthy", () => {
    expect(queueDepthIsMeaningful("healthy")).toBe(true);
  });
});

describe("overallStatus", () => {
  it("is operational only when every dependency is healthy", () => {
    expect(overallStatus(["healthy", "healthy", "healthy"])).toBe("operational");
  });

  it("is degraded when any dependency is unavailable", () => {
    expect(overallStatus(["healthy", "unhealthy", "healthy"])).toBe("degraded");
    expect(overallStatus(["unhealthy", "unhealthy", "unhealthy"])).toBe("degraded");
  });

  it("is unknown when something is indeterminate but nothing has failed", () => {
    expect(overallStatus(["healthy", "unknown", "healthy"])).toBe("unknown");
  });

  it("prefers degraded over unknown when both are present", () => {
    // A known failure is more actionable than an indeterminate reading.
    expect(overallStatus(["unknown", "unhealthy"])).toBe("degraded");
  });
});

describe("STATUS_LABEL", () => {
  it("does not label anything as a live worker count or a false healthy", () => {
    expect(STATUS_LABEL.unhealthy).toBe("Unavailable");
    expect(STATUS_LABEL.unknown).toBe("Unknown");
    expect(STATUS_LABEL.disabled).toBe("Disabled");
  });
});
