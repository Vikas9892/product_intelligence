/**
 * Operational status vocabulary.
 *
 * `healthy` / `unhealthy` are the literal strings the backend emits. The others
 * are frontend-side distinctions for things the backend cannot report:
 *
 * - `unknown` — the value could not be determined, or a value was returned but
 *   is not trustworthy (see `queueDepthIsMeaningful`).
 * - `disabled` — the feature is switched off, so there is nothing to report.
 */
export type OperationalStatus = "healthy" | "unhealthy" | "unknown" | "disabled";

/** Maps a backend health string onto the status vocabulary. */
export function toStatus(value: string | null | undefined): OperationalStatus {
  if (value === "healthy") return "healthy";
  if (value === "unhealthy") return "unhealthy";
  return "unknown";
}

export const STATUS_LABEL: Record<OperationalStatus, string> = {
  healthy: "Healthy",
  unhealthy: "Unavailable",
  unknown: "Unknown",
  disabled: "Disabled",
};

/**
 * Whether `queue_depth` means anything right now.
 *
 * `SystemHealthService` wraps every dependency read so a failure degrades to
 * `0` instead of raising. That makes a reported depth of 0 ambiguous when Redis
 * is unhealthy: it could be an empty queue, or it could be the fallback for a
 * read that never happened. The queue lives in Redis, so when Redis is
 * unhealthy the number is reported as unknown rather than as zero.
 */
export function queueDepthIsMeaningful(redisStatus: OperationalStatus): boolean {
  return redisStatus === "healthy";
}

/**
 * Overall posture, derived from the dependency statuses.
 *
 * The API itself is healthy by construction whenever a response was received —
 * a body arrived, so the service is up. A dependency being down makes the
 * platform degraded, not the API unreachable.
 */
export function overallStatus(
  statuses: OperationalStatus[],
): "operational" | "degraded" | "unknown" {
  if (statuses.some((s) => s === "unhealthy")) return "degraded";
  if (statuses.every((s) => s === "healthy")) return "operational";
  return "unknown";
}
